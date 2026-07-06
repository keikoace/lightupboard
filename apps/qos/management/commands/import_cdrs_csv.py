"""
Fast CDR import using PostgreSQL COPY FROM STDIN.
Falls back to bulk_create for SQLite.

Usage:
    py manage.py import_cdrs_csv path/to/file.csv.gz --alias "threeutelecom=3U Telecom"
"""
import csv, gzip, hashlib, io, math, os, re
from datetime import datetime, timezone, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.models import Company
from apps.qos.models import CDR

ANSWERED = {'answered', 'normal clearing', 'normal call clearing'}
REASON_CODE_MAP = {
    'answered': 16, 'normal clearing': 16, 'normal call clearing': 16,
    'busy': 17, 'user busy': 17, 'no answer': 18, 'no user responding': 18,
    'cancel': 21, 'call rejected': 21, 'unallocated number': 1,
    'subscriber absent': 20, 'congestion': 34, 'failed': 41,
}
_HEX_SUFFIX = re.compile(r'-[0-9a-f]{6,8}$', re.IGNORECASE)


def _supplier(egress):
    name = egress.strip()
    if name.upper().startswith('SIP/'):
        name = name[4:]
    name = re.sub(r'-out\d+.*$', '', name, flags=re.IGNORECASE)
    return _HEX_SUFFIX.sub('', name)


def _call_id(start_s, ani, dnis, egress):
    return hashlib.sha1(f'{start_s}|{ani}|{dnis}|{egress}'.encode()).hexdigest()[:24]


def _dt(v):
    v = v.strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _f(v):
    try:
        return float(v.strip())
    except:
        return 0.0


def _open(path):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, encoding='utf-8', errors='replace')


class Command(BaseCommand):
    help = 'Fast CDR import (PostgreSQL COPY or bulk_create fallback).'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--alias', action='append', default=[], metavar='FROM=TO')
        parser.add_argument('--answered-only', action='store_true')

    def handle(self, *args, **options):
        path      = options['file']
        ans_only  = options['answered_only']

        if not os.path.exists(path):
            raise CommandError(f'File not found: {path}')

        # ── alias map ─────────────────────────────────────────────────────────
        alias = {}
        for p in options['alias']:
            if '=' in p:
                s, _, d = p.partition('=')
                alias[s.strip().lower()] = d.strip()
                self.stdout.write(f'  Alias: "{s.strip()}" → "{d.strip()}"')

        # ── company cache ─────────────────────────────────────────────────────
        co_cache = {}
        def get_co(name):
            name = name.strip()
            real = alias.get(name.lower(), name)
            key  = real.lower()
            if key not in co_cache:
                try:
                    co_cache[key] = Company.objects.get(name__iexact=real)
                except Company.DoesNotExist:
                    qs = Company.objects.filter(name__icontains=real)
                    co_cache[key] = qs.first() if qs.count() == 1 else None
                    if co_cache[key]:
                        self.stdout.write(f'  Fuzzy: "{name}" → "{co_cache[key].name}"')
                    else:
                        self.stdout.write(self.style.WARNING(f'  Not found: "{real}"'))
                except Company.MultipleObjectsReturned:
                    co_cache[key] = Company.objects.filter(name__iexact=real).first()
            return co_cache[key]

        # ── CDR table column order for COPY ───────────────────────────────────
        # Must match exactly the columns we write below
        COPY_COLS = (
            'call_id', 'switch_id', 'customer_id', 'supplier_id',
            'ani', 'dnis',
            'start_time', 'answer_time', 'end_time',
            'duration_sec', 'switch_billed_sec',
            'buy_billed_duration_sec', 'sell_billed_duration_sec',
            'buy_rate', 'sell_rate', 'buy_cost', 'sell_revenue',
            'disconnect_cause', 'is_processed',
        )

        is_pg = 'postgresql' in connection.settings_dict['ENGINE']

        self.stdout.write(f'Reading {path} …')

        seen      = set()
        total     = 0
        inserted  = 0
        skipped   = 0

        if is_pg:
            # ── PostgreSQL COPY path ──────────────────────────────────────────
            buf = io.StringIO()

            def flush_buf():
                nonlocal inserted
                if buf.tell() == 0:
                    return
                buf.seek(0)
                tbl = CDR._meta.db_table
                cols = ','.join(f'"{c}"' for c in COPY_COLS)
                with connection.cursor() as cur:
                    cur.copy_expert(
                        f'COPY "{tbl}" ({cols}) FROM STDIN WITH (FORMAT csv, NULL \'\\N\')',
                        buf,
                    )
                inserted += buf.getvalue().count('\n')
                buf.truncate(0)
                buf.seek(0)

            writer = csv.writer(buf)

            with _open(path) as fh:
                reader = csv.DictReader(fh)
                reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]

                for row in reader:
                    total += 1
                    ani     = (row.get('A Number (CLI)') or '').strip()[:30]
                    dnis    = (row.get('B Number (DNIS)') or '').strip()[:30]
                    ingress = (row.get('Ingress(Customer)') or '').strip()
                    egress  = (row.get('Egress (Supplier)') or '').strip()
                    start_s = (row.get('Start Date') or '').strip()
                    end_s   = (row.get('End Date') or '').strip()
                    dur_s   = (row.get('Actual Duration') or '').strip()
                    bil_s   = (row.get('Billed Duration') or '').strip()
                    reason  = (row.get('SIP Reason / Disconnect Reason') or '').strip()

                    is_ans  = reason.lower() in ANSWERED
                    if ans_only and not is_ans:
                        skipped += 1
                        continue

                    st = _dt(start_s)
                    if st is None:
                        skipped += 1
                        continue

                    cid = _call_id(start_s, ani, dnis, egress)
                    if cid in seen:
                        skipped += 1
                        continue
                    seen.add(cid)

                    et        = _dt(end_s)
                    dur_f     = _f(dur_s)
                    dur_sec   = max(0, int(dur_f))
                    bil_f     = _f(bil_s)
                    sw_billed = max(0, math.ceil(bil_f))

                    ans_time = None
                    if is_ans and et and dur_f > 0:
                        ans_time = et - timedelta(seconds=dur_f)

                    cust = get_co(ingress)
                    supp = get_co(_supplier(egress))
                    cause = REASON_CODE_MAP.get(reason.lower())

                    def _v(x):
                        return r'\N' if x is None else str(x)

                    writer.writerow([
                        cid,
                        _v(None),                          # switch_id
                        _v(cust.pk if cust else None),
                        _v(supp.pk if supp else None),
                        ani, dnis,
                        st.strftime('%Y-%m-%d %H:%M:%S+00'),
                        ans_time.strftime('%Y-%m-%d %H:%M:%S+00') if ans_time else r'\N',
                        et.strftime('%Y-%m-%d %H:%M:%S+00') if et else r'\N',
                        dur_sec, sw_billed,
                        0, 0,        # buy/sell billed (set by process_cdrs)
                        0, 0, 0, 0,  # rates/costs
                        _v(cause),
                        'false',
                    ])

                    if total % 50000 == 0:
                        flush_buf()
                        self.stdout.write(f'  … {total:,} rows read, {inserted:,} inserted')

            flush_buf()

        else:
            # ── SQLite fallback: bulk_create ──────────────────────────────────
            batch = []
            with _open(path) as fh:
                reader = csv.DictReader(fh)
                reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
                for row in reader:
                    total += 1
                    ani     = (row.get('A Number (CLI)') or '').strip()[:30]
                    dnis    = (row.get('B Number (DNIS)') or '').strip()[:30]
                    ingress = (row.get('Ingress(Customer)') or '').strip()
                    egress  = (row.get('Egress (Supplier)') or '').strip()
                    start_s = (row.get('Start Date') or '').strip()
                    end_s   = (row.get('End Date') or '').strip()
                    dur_s   = (row.get('Actual Duration') or '').strip()
                    bil_s   = (row.get('Billed Duration') or '').strip()
                    reason  = (row.get('SIP Reason / Disconnect Reason') or '').strip()

                    is_ans = reason.lower() in ANSWERED
                    if ans_only and not is_ans:
                        skipped += 1
                        continue
                    st = _dt(start_s)
                    if not st:
                        skipped += 1
                        continue
                    cid = _call_id(start_s, ani, dnis, egress)
                    if cid in seen:
                        skipped += 1
                        continue
                    seen.add(cid)
                    et        = _dt(end_s)
                    dur_f     = _f(dur_s)
                    sw_billed = max(0, math.ceil(_f(bil_s)))
                    ans_time  = (et - timedelta(seconds=dur_f)) if (is_ans and et and dur_f > 0) else None
                    cust = get_co(ingress)
                    supp = get_co(_supplier(egress))
                    batch.append(CDR(
                        call_id=cid, switch=None,
                        customer=cust, supplier=supp,
                        ani=ani, dnis=dnis,
                        start_time=st, answer_time=ans_time, end_time=et,
                        duration_sec=max(0, int(dur_f)),
                        switch_billed_sec=sw_billed,
                        disconnect_cause=REASON_CODE_MAP.get(reason.lower()),
                        is_processed=False,
                    ))
                    if len(batch) >= 2000:
                        CDR.objects.bulk_create(batch, ignore_conflicts=True)
                        inserted += len(batch)
                        batch.clear()
                        self.stdout.write(f'  … {total:,} rows, {inserted:,} inserted')
            if batch:
                CDR.objects.bulk_create(batch, ignore_conflicts=True)
                inserted += len(batch)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone.\n'
            f'  Rows read : {total:,}\n'
            f'  Inserted  : {inserted:,}\n'
            f'  Skipped   : {skipped:,}\n'
        ))
        if inserted:
            self.stdout.write('Run: py manage.py process_cdrs')
