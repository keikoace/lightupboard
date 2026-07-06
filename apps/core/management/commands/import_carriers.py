"""
Import carriers from a tab-delimited export file into Company + Trunk records.

Logic
-----
- A row where Carrier Name == Master Carrier  →  top-level Company
- A row where Carrier Name != Master Carrier  →  Trunk under the master Company

Role is derived from tariff columns:
  has buy + sell → both  |  buy only → supplier  |  sell only → customer

Usage
-----
    python manage.py import_carriers path/to/export.txt [--dry-run] [--update]

Flags
-----
  --dry-run   Print actions without writing anything.
  --update    Overwrite existing Company / Trunk records (default: skip).
"""
import csv
import io
import zipfile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.core.models import Company, Trunk


TERMS_MAP = {
    'pre-payment':         'PrePay',
    'prepayment':          'PrePay',
    'pre payment':         'PrePay',
    'payment terms 30/7':  '30/7',
    'payment terms 30/10': '30/10',
    'payment terms 30/15': '30/15',
    'payment terms 30/30': '30/30',
    'payment terms 30/60': '30/60',
    'payment terms 15/7':  '15/7',
    'payment terms 15/15': '15/15',
    'payment terms 7/7':   '7/7',
    'payment terms 7/3':   '7/3',
    '--none--':            '',
    '':                    '',
}

NO_TARIFF = {'--- none ---', '--- pending ---', ''}


def _map_terms(raw):
    return TERMS_MAP.get(raw.strip().lower(), '')


def _has_tariff(raw):
    return raw.strip().lower() not in NO_TARIFF


def _build_address(*parts):
    return '\n'.join(p for p in parts if p.strip())


def _parse_role(has_buy, has_sell, type_):
    if type_.lower() == 'internal':
        return Company.ROLE_BOTH
    if has_buy and has_sell:
        return Company.ROLE_BOTH
    if has_buy:
        return Company.ROLE_SUPPLIER
    if has_sell:
        return Company.ROLE_CUSTOMER
    return Company.ROLE_BOTH


def _load_rows(path):
    if path.lower().endswith('.zip'):
        with zipfile.ZipFile(path) as zf:
            data = zf.read(zf.namelist()[0]).decode('utf-8-sig')
    else:
        with open(path, encoding='utf-8-sig') as fh:
            data = fh.read()
    return list(csv.DictReader(io.StringIO(data), delimiter='\t', quotechar='"'))


class Command(BaseCommand):
    help = 'Import carriers from tab-delimited export into Company + Trunk records'

    def add_arguments(self, parser):
        parser.add_argument('file', help='Tab-delimited carrier export (.txt or .zip)')
        parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
        parser.add_argument('--update', action='store_true',
                            help='Update existing records (default: skip)')

    def handle(self, *args, **options):
        path      = options['file']
        dry_run   = options['dry_run']
        do_update = options['update']

        try:
            rows = _load_rows(path)
        except FileNotFoundError:
            raise CommandError(f'File not found: {path}')

        # ── Pass 1: collect all master-carrier names so we can ensure
        #            Company records exist before creating Trunks.
        masters = {}   # master_name → row (first occurrence wins)
        trunks  = []   # rows that are sub-carriers

        for row in rows:
            name   = row.get('Carrier Name', '').strip()
            master = row.get('Master Carrier', '').strip()
            if not name:
                continue
            if name == master or not master:
                # This row IS the master company (or has no master stated).
                if master not in masters:
                    masters[master or name] = row
            else:
                trunks.append(row)

        # Some trunks reference a master that may not have its own top-level row.
        # Ensure every referenced master has an entry.
        for row in trunks:
            master = row.get('Master Carrier', '').strip()
            if master and master not in masters:
                # Use the trunk row itself as a template for the company
                masters[master] = row

        co_created = co_updated = co_skipped = 0
        tr_created = tr_updated = tr_skipped = 0

        with transaction.atomic():
            # ── Pass 2: upsert Companies ─────────────────────────────────────
            company_cache = {}   # name → Company instance

            for master_name, row in masters.items():
                buy_t  = row.get('Tariff (Buying)', '').strip()
                sell_t = row.get('Tariff (Selling)', '').strip()
                type_  = row.get('Type', '').strip()
                role   = _parse_role(_has_tariff(buy_t), _has_tariff(sell_t), type_)

                cust_terms = _map_terms(row.get('Customer Payment Terms', ''))
                supp_terms = _map_terms(row.get('Supplier Payment Terms', ''))
                payment_terms = cust_terms or supp_terms

                address = _build_address(
                    row.get('Addr.Line 1', ''), row.get('Addr.Line 2', ''),
                    row.get('Addr.Line 3', ''), row.get('Addr.Line 4', ''),
                    row.get('Post Code', ''),
                )
                vat_str   = row.get('VAT %', '').strip()
                vat_exempt = (vat_str == '0.00')
                is_active  = row.get('Status', '').strip().lower() == 'active'
                phone      = row.get('Telephone', '').strip() or row.get('Mobile', '').strip()
                country    = row.get('Country', '').strip()

                notes_parts = []
                abbr = row.get('Carr. Abbr. Name', '').strip()
                if abbr:
                    notes_parts.append(f'Abbr: {abbr}')
                inv_name = row.get('Carr. Invoice Name', '').strip()
                if inv_name:
                    notes_parts.append(f'Invoice name: {inv_name}')
                contact = row.get('Contact', '').strip()
                if contact:
                    notes_parts.append(f'Contact: {contact}')
                vat_no = row.get('VAT No.', '').strip()
                if vat_no:
                    notes_parts.append(f'VAT No: {vat_no}')
                inv_from = row.get('Company Invoiced From', '').strip()
                if inv_from:
                    notes_parts.append(f'Invoiced from: {inv_from}')
                billing_cycle = row.get('Billing Cycle', '').strip()
                if billing_cycle:
                    notes_parts.append(f'Billing cycle: {billing_cycle}')
                if type_.lower() == 'internal':
                    notes_parts.append('Type: Internal')
                notes = '\n'.join(notes_parts)

                existing = Company.objects.filter(name=master_name).first()
                if existing:
                    company_cache[master_name] = existing
                    if do_update:
                        if not dry_run:
                            existing.role          = role
                            existing.address       = address
                            existing.country       = country
                            existing.phone         = phone
                            existing.payment_terms = payment_terms
                            existing.vat_exempt    = vat_exempt
                            existing.is_active     = is_active
                            existing.notes         = notes
                            existing.save()
                        co_updated += 1
                        self.stdout.write(f'  CO UPDATE  {master_name}')
                    else:
                        co_skipped += 1
                        self.stdout.write(f'  CO skip    {master_name}')
                else:
                    if not dry_run:
                        co = Company.objects.create(
                            name=master_name,
                            role=role,
                            address=address,
                            country=country,
                            phone=phone,
                            payment_terms=payment_terms,
                            vat_exempt=vat_exempt,
                            is_active=is_active,
                            notes=notes,
                        )
                        company_cache[master_name] = co
                    co_created += 1
                    self.stdout.write(f'  CO CREATE  {master_name}')

            # Refresh cache with any existing companies not in masters dict
            for name in list(company_cache.keys()):
                pass  # already populated above

            # ── Pass 3: upsert Trunks ────────────────────────────────────────
            for row in trunks:
                trunk_name  = row.get('Carrier Name', '').strip()
                master_name = row.get('Master Carrier', '').strip()

                parent = company_cache.get(master_name)
                if parent is None and not dry_run:
                    parent = Company.objects.filter(name=master_name).first()
                if parent is None:
                    self.stderr.write(f'  TR WARN    {trunk_name}: master "{master_name}" not found — skipped')
                    continue

                abbr      = row.get('Carr. Abbr. Name', '').strip()
                buy_t     = row.get('Tariff (Buying)', '').strip()
                sell_t    = row.get('Tariff (Selling)', '').strip()
                type_     = row.get('Type', '').strip()
                is_active = row.get('Status', '').strip().lower() == 'active'

                # Direction: infer from tariff presence
                has_buy  = _has_tariff(buy_t)
                has_sell = _has_tariff(sell_t)
                if has_buy and not has_sell:
                    direction = Trunk.DIRECTION_OUT
                elif has_sell and not has_buy:
                    direction = Trunk.DIRECTION_IN
                else:
                    direction = Trunk.DIRECTION_BOTH

                notes_parts = []
                if buy_t and has_buy:
                    notes_parts.append(f'Buy tariff: {buy_t}')
                if sell_t and has_sell:
                    notes_parts.append(f'Sell tariff: {sell_t}')
                inv_from = row.get('Company Invoiced From', '').strip()
                if inv_from:
                    notes_parts.append(f'Invoiced from: {inv_from}')
                billing_cycle = row.get('Billing Cycle', '').strip()
                if billing_cycle:
                    notes_parts.append(f'Billing cycle: {billing_cycle}')
                if type_.lower() == 'internal':
                    notes_parts.append('Type: Internal')
                trunk_notes = '\n'.join(notes_parts)

                if not dry_run:
                    existing_tr = Trunk.objects.filter(company=parent, name=trunk_name).first()
                else:
                    existing_tr = None  # can't query reliably in dry-run

                if existing_tr:
                    if do_update:
                        if not dry_run:
                            existing_tr.abbreviation = abbr
                            existing_tr.direction    = direction
                            existing_tr.is_active    = is_active
                            existing_tr.notes        = trunk_notes
                            existing_tr.save()
                        tr_updated += 1
                        self.stdout.write(f'  TR UPDATE  {master_name} / {trunk_name}')
                    else:
                        tr_skipped += 1
                        self.stdout.write(f'  TR skip    {master_name} / {trunk_name}')
                else:
                    if not dry_run:
                        Trunk.objects.create(
                            company=parent,
                            name=trunk_name,
                            abbreviation=abbr,
                            direction=direction,
                            is_active=is_active,
                            notes=trunk_notes,
                        )
                    tr_created += 1
                    self.stdout.write(f'  TR CREATE  {master_name} / {trunk_name}')

            if dry_run:
                transaction.set_rollback(True)

        mode = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'\n{mode}Companies — created: {co_created}, updated: {co_updated}, skipped: {co_skipped}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'{mode}Trunks    — created: {tr_created}, updated: {tr_updated}, skipped: {tr_skipped}'
        ))
