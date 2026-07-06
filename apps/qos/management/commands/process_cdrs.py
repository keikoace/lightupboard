"""
process_cdrs — rate-cost all unprocessed CDRs.

For PostgreSQL: executes a single bulk SQL UPDATE using CASE WHEN for prefix
matching — processes 800K+ CDRs in seconds.

For SQLite: falls back to chunked Python processing.

Usage
-----
    py manage.py process_cdrs                  # process new CDRs
    py manage.py process_cdrs --reprocess      # re-rate ALL CDRs
    py manage.py process_cdrs --dry-run        # show stats, no writes
"""
import math
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.qos.models import CDR
from apps.rates.models import Tariff, Rate, OriginGroup, OriginDialcode


def _billed_seconds(duration, minimum, increment):
    if duration <= 0:
        return 0
    if duration <= minimum:
        return minimum
    return minimum + math.ceil((duration - minimum) / increment) * increment


def _cost(billed_sec, rate_per_minute):
    if not billed_sec or not rate_per_minute:
        return Decimal('0')
    return (Decimal(billed_sec) / 60 * Decimal(str(rate_per_minute))).quantize(
        Decimal('0.0001'), rounding=ROUND_HALF_UP
    )


def _longest_prefix_match(number, prefix_map):
    for length in range(min(len(number), 7), 0, -1):
        if number[:length] in prefix_map:
            return prefix_map[number[:length]]
    return None


class Command(BaseCommand):
    help = 'Rate-cost CDRs. Uses fast SQL UPDATE on PostgreSQL.'

    def add_arguments(self, parser):
        parser.add_argument('--reprocess', action='store_true',
            help='Re-rate ALL CDRs, not just unprocessed ones.')
        parser.add_argument('--dry-run', action='store_true',
            help='Show what would happen without writing.')

    def handle(self, *args, **options):
        reprocess = options['reprocess']
        dry_run   = options['dry_run']

        is_pg = 'postgresql' in connection.settings_dict['ENGINE']
        self.stdout.write(f'Engine: {"PostgreSQL ✓" if is_pg else "SQLite"}')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no writes.\n'))

        # ── Load tariffs and rates ────────────────────────────────────────────
        sell_tariff = {}  # company_id → tariff
        buy_tariff  = {}
        for t in Tariff.objects.filter(is_active=True).select_related('company').order_by('company_id', '-effective_date'):
            if t.side == 'sell' and t.company_id not in sell_tariff:
                sell_tariff[t.company_id] = t
            elif t.side == 'buy' and t.company_id not in buy_tariff:
                buy_tariff[t.company_id] = t

        # rate_map: tariff_id → list of (prefix, rate, min_sec, incr_sec, origin_group_id|None)
        rate_map = {}
        for r in Rate.objects.filter(tariff__is_active=True).select_related('tariff').order_by('-prefix'):
            rate_map.setdefault(r.tariff_id, []).append(
                (r.prefix, float(r.rate_per_minute), r.minimum_duration_sec,
                 r.billing_increment_sec, r.origin_group_id)
            )

        # origin_map: ani_prefix → origin_group_id  (longest-prefix match on ANI)
        origin_map = {}
        for od in OriginDialcode.objects.select_related('group'):
            origin_map[od.prefix] = od.group_id

        self.stdout.write(f'Sell tariffs: {len(sell_tariff)} | Buy tariffs: {len(buy_tariff)}')
        total_rates = sum(len(v) for v in rate_map.values())
        origin_rate_count = sum(1 for rates in rate_map.values() for r in rates if r[4] is not None)
        self.stdout.write(f'Rates loaded: {total_rates} ({origin_rate_count} origin-based)')
        self.stdout.write(f'Origin ANI prefixes: {len(origin_map)}')

        if is_pg and not dry_run:
            self._process_pg(sell_tariff, buy_tariff, rate_map, origin_map, reprocess)
        else:
            self._process_python(sell_tariff, buy_tariff, rate_map, origin_map, reprocess, dry_run)

    # ── PostgreSQL fast path ──────────────────────────────────────────────────

    def _process_pg(self, sell_tariff, buy_tariff, rate_map, origin_map, reprocess):
        """
        Build SQL UPDATE statements with CASE WHEN prefix matching.
        Origin-based rates are checked first (ANI + DNIS match), then standard rates.
        """
        self.stdout.write('Building SQL…')

        total_updated = 0
        from apps.core.models import Destination

        dest_map = {d.prefix: d.id for d in Destination.objects.filter(is_active=True)}
        dest_sorted = sorted(dest_map.items(), key=lambda x: -len(x[0]))
        dest_case = '\n          '.join(
            f"WHEN dnis LIKE '{pfx}%' THEN {did}"
            for pfx, did in dest_sorted
        )

        # Build ANI → origin_group_id lookup sorted longest-first
        ani_sorted = sorted(origin_map.items(), key=lambda x: -len(x[0]))

        tbl = CDR._meta.db_table  # define before loop so cleanup step always has it

        for company_id, tariff in sell_tariff.items():
            all_rates = rate_map.get(tariff.id, [])
            if not all_rates:
                self.stdout.write(self.style.WARNING(f'  No rates for tariff {tariff.id}, skipping'))
                continue

            # Split into origin-specific and standard rates
            origin_rates   = [(p, r, mn, inc, gid) for p, r, mn, inc, gid in all_rates if gid is not None]
            standard_rates = [(p, r, mn, inc) for p, r, mn, inc, gid in all_rates if gid is None]

            # Sort longest prefix first
            origin_rates   = sorted(origin_rates,   key=lambda x: -len(x[0]))
            standard_rates = sorted(standard_rates, key=lambda x: -len(x[0]))

            # Build CASE WHEN for sell_rate:
            # Origin-based entries: check BOTH ANI prefix AND DNIS prefix
            # Standard entries: check DNIS prefix only (fallback)
            rate_cases   = []
            revenue_cases = []

            # ANI-aware CASE entries for origin rates
            # Group by origin_group_id so we can build efficient CASE
            from collections import defaultdict
            by_group = defaultdict(list)
            for p, r, mn, inc, gid in origin_rates:
                by_group[gid].append((p, r))

            for gid, group_rates in by_group.items():
                # Find ANI prefixes for this group
                ani_prefixes = [ani for ani, og_id in origin_map.items() if og_id == gid]
                if not ani_prefixes:
                    continue
                for ani_pfx in sorted(ani_prefixes, key=len, reverse=True):
                    for dnis_pfx, rate in sorted(group_rates, key=lambda x: -len(x[0])):
                        rate_cases.append(
                            f"WHEN ani LIKE '{ani_pfx}%' AND dnis LIKE '{dnis_pfx}%' THEN {rate:.6f}"
                        )
                        revenue_cases.append(
                            f"WHEN ani LIKE '{ani_pfx}%' AND dnis LIKE '{dnis_pfx}%' THEN "
                            f"(switch_billed_sec::numeric / 60.0 * {rate:.6f})"
                        )

            # Standard (non-origin) CASE entries
            for p, r, mn, inc in standard_rates:
                rate_cases.append(f"WHEN dnis LIKE '{p}%' THEN {r:.6f}")
                revenue_cases.append(
                    f"WHEN dnis LIKE '{p}%' THEN (switch_billed_sec::numeric / 60.0 * {r:.6f})"
                )

            if not rate_cases:
                continue

            sell_rate_case  = '\n          '.join(rate_cases)
            revenue_case    = '\n          '.join(revenue_cases)

            where_clause = f"WHERE customer_id = {company_id}" + (
                " AND is_processed = false" if not reprocess else ""
            )

            sql = f"""
UPDATE {tbl} SET
    sell_rate = CASE
          {sell_rate_case}
          ELSE 0 END,
    sell_billed_duration_sec = CASE
          WHEN answer_time IS NOT NULL AND switch_billed_sec > 0
          THEN switch_billed_sec
          ELSE 0 END,
    sell_revenue = CASE
          WHEN answer_time IS NOT NULL AND switch_billed_sec > 0
          THEN ROUND(CASE
            {revenue_case}
            ELSE 0 END, 4)
          ELSE 0 END,
    destination_id = CASE
          {dest_case}
          ELSE destination_id END,
    is_processed = true
{where_clause}
"""
            self.stdout.write(f'Running SQL UPDATE for customer_id={company_id}…')
            with connection.cursor() as cur:
                cur.execute(sql)
                n = cur.rowcount
                total_updated += n
            self.stdout.write(self.style.SUCCESS(f'  Updated {n:,} CDRs'))

        # ── Buy-side pass (per supplier) ──────────────────────────────────────
        for company_id, tariff in buy_tariff.items():
            rates = rate_map.get(tariff.id, [])
            if not rates:
                continue

            rates_sorted = sorted(rates, key=lambda x: -len(x[0]))

            buy_rate_case = '\n          '.join(
                f"WHEN dnis LIKE '{p}%' THEN {r:.6f}"
                for p, r, mn, inc, *_ in rates_sorted
            )
            buy_revenue_case = '\n          '.join(
                f"WHEN dnis LIKE '{p}%' THEN (switch_billed_sec::numeric / 60.0 * {r:.6f})"
                for p, r, mn, inc, *_ in rates_sorted
            )

            where_clause = f"WHERE supplier_id = {company_id}" + (
                " AND is_processed = false" if not reprocess else ""
            )

            sql = f"""
UPDATE {tbl} SET
    buy_rate = CASE
          {buy_rate_case}
          ELSE 0 END,
    buy_billed_duration_sec = CASE
          WHEN answer_time IS NOT NULL AND switch_billed_sec > 0
          THEN switch_billed_sec
          ELSE 0 END,
    buy_cost = CASE
          WHEN answer_time IS NOT NULL AND switch_billed_sec > 0
          THEN ROUND(CASE
            {buy_revenue_case}
            ELSE 0 END, 4)
          ELSE 0 END
{where_clause}
"""
            self.stdout.write(f'Running buy SQL UPDATE for supplier_id={company_id}…')
            with connection.cursor() as cur:
                cur.execute(sql)
                n = cur.rowcount
                total_updated += n
            self.stdout.write(self.style.SUCCESS(f'  Updated {n:,} CDRs (buy side)'))

        # Mark remaining unprocessed CDRs (no tariff match) as processed
        with connection.cursor() as cur:
            cur.execute(f"UPDATE {tbl} SET is_processed = true WHERE is_processed = false")
            n = cur.rowcount
            if n:
                self.stdout.write(f'  Marked {n:,} CDRs processed (no tariff match)')

        self.stdout.write(self.style.SUCCESS(f'\nDone. Total updated: {total_updated:,}'))

    # ── Python fallback (SQLite) ──────────────────────────────────────────────

    def _process_python(self, sell_tariff, buy_tariff, rate_map, origin_map, reprocess, dry_run):
        from apps.core.models import Destination
        prefix_map = {d.prefix: d for d in Destination.objects.filter(is_active=True)}

        UPDATE_FIELDS = [
            'destination', 'sell_billed_duration_sec', 'buy_billed_duration_sec',
            'sell_rate', 'buy_rate', 'sell_revenue', 'buy_cost', 'is_processed',
        ]

        # Pre-build flat lookups and sorted prefix-length lists per tariff
        # rate_map entries: (prefix, rate, min, incr, origin_group_id)
        flat_rate_map = {}       # (tid, prefix, origin_group_id) → (rate, mn, inc)
        rate_lengths  = {}       # tid → sorted list of prefix lengths (standard rates)
        origin_lengths = {}      # tid → sorted list of prefix lengths (origin rates)

        for tid, rates in rate_map.items():
            std_lens = set()
            org_lens = set()
            for prefix, rate, mn, inc, gid in rates:
                flat_rate_map[(tid, prefix, gid)] = (rate, mn, inc)
                if gid is None:
                    std_lens.add(len(prefix))
                else:
                    org_lens.add(len(prefix))
            rate_lengths[tid]   = sorted(std_lens, reverse=True)
            origin_lengths[tid] = sorted(org_lens, reverse=True)

        # ANI prefix → origin_group_id (sorted longest-first for matching)
        ani_prefix_lengths = sorted({len(p) for p in origin_map}, reverse=True)

        processed = no_rate = no_dest = 0
        done = 0

        qs_filter = CDR.objects.all() if reprocess else CDR.objects.filter(is_processed=False)

        while True:
            cdrs = list(qs_filter.select_related('customer', 'supplier').order_by('id')[:500])
            if not cdrs:
                break
            batch = []
            for cdr in cdrs:
                dnis = (cdr.dnis or '').lstrip('+')
                dest = _longest_prefix_match(dnis, prefix_map)
                if dest is None:
                    no_dest += 1
                    cdr.is_processed = True
                    batch.append(cdr)
                    continue

                is_ans = cdr.answer_time is not None and cdr.switch_billed_sec > 0
                sell_rate_val = buy_rate_val = Decimal('0')
                sell_min = sell_incr = buy_min = buy_incr = 1
                found = False

                ani = (cdr.ani or '').lstrip('+')

                # Resolve origin group from ANI (longest-prefix match)
                ani_group_id = None
                for length in ani_prefix_lengths:
                    ani_group_id = origin_map.get(ani[:length])
                    if ani_group_id is not None:
                        break

                if cdr.customer_id and cdr.customer_id in sell_tariff:
                    tid = sell_tariff[cdr.customer_id].id

                    # 1) Try origin-specific rate first (ANI group + DNIS prefix)
                    if ani_group_id is not None:
                        for length in origin_lengths.get(tid, []):
                            key = (tid, dnis[:length], ani_group_id)
                            if key in flat_rate_map:
                                sell_rate_val, sell_min, sell_incr = flat_rate_map[key]
                                sell_rate_val = Decimal(str(sell_rate_val))
                                found = True
                                break

                    # 2) Fall back to standard rate
                    if not found:
                        for length in rate_lengths.get(tid, []):
                            key = (tid, dnis[:length], None)
                            if key in flat_rate_map:
                                sell_rate_val, sell_min, sell_incr = flat_rate_map[key]
                                sell_rate_val = Decimal(str(sell_rate_val))
                                found = True
                                break

                if not found:
                    no_rate += 1

                if cdr.supplier_id and cdr.supplier_id in buy_tariff:
                    tid = buy_tariff[cdr.supplier_id].id
                    # Origin rates on buy side too (if vendor uses origin billing)
                    if ani_group_id is not None:
                        for length in origin_lengths.get(tid, []):
                            key = (tid, dnis[:length], ani_group_id)
                            if key in flat_rate_map:
                                buy_rate_val, buy_min, buy_incr = flat_rate_map[key]
                                buy_rate_val = Decimal(str(buy_rate_val))
                                break
                    if not buy_rate_val:
                        for length in rate_lengths.get(tid, []):
                            key = (tid, dnis[:length], None)
                            if key in flat_rate_map:
                                buy_rate_val, buy_min, buy_incr = flat_rate_map[key]
                                buy_rate_val = Decimal(str(buy_rate_val))
                                break

                sb = cdr.switch_billed_sec if is_ans else 0
                sell_billed = _billed_seconds(sb, sell_min, sell_incr) if is_ans else 0
                buy_billed  = _billed_seconds(sb, buy_min, buy_incr)  if is_ans else 0

                cdr.destination              = dest
                cdr.sell_billed_duration_sec = sell_billed
                cdr.buy_billed_duration_sec  = buy_billed
                cdr.sell_rate                = sell_rate_val
                cdr.buy_rate                 = buy_rate_val
                cdr.sell_revenue             = _cost(sell_billed, sell_rate_val)
                cdr.buy_cost                 = _cost(buy_billed,  buy_rate_val)
                cdr.is_processed             = True
                batch.append(cdr)
                processed += 1

            if batch and not dry_run:
                CDR.objects.bulk_update(batch, UPDATE_FIELDS, batch_size=100)
            done += len(cdrs)
            self.stdout.write(f'  {done:,} done (rated={processed:,} no_dest={no_dest:,} no_rate={no_rate:,})')
            if dry_run:
                break

        self.stdout.write(self.style.SUCCESS(f'\nDone. Rated={processed:,} no_dest={no_dest:,} no_rate={no_rate:,}'))
