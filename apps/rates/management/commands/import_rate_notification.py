"""
import_rate_notification — Import a vendor rate notification Excel file.

Handles the standard 4-sheet format:
  Sheet 1 — Prices                       (standard A-Z rates)
  Sheet 2 — Dialcodes                    (destination prefix mappings)
  Sheet 3 — Origin Based Billing Prices  (origin-specific rates)
  Sheet 4 — Origin Based Billing Dialcodes (ANI prefix → origin group)

Usage:
    python manage.py import_rate_notification <xlsx_file> --tariff <tariff_id>
    python manage.py import_rate_notification rate_sheet.xlsx --tariff 3 --dry-run
    python manage.py import_rate_notification rate_sheet.xlsx --tariff 3 --effective 2026-06-12

Options:
    --tariff        Required. Tariff ID to import rates into.
    --effective     Override the effective date from the file (YYYY-MM-DD).
    --dry-run       Parse and report without writing anything.
    --skip-standard Skip the standard A-Z rates (import origin-based only).
    --skip-origin   Skip origin-based rates (import standard only).
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.rates.models import Tariff, Rate, OriginGroup, OriginDialcode
from apps.core.models import Destination


def _parse_billing(value):
    """Parse '60/6' → (60, 6). Returns (1, 1) on failure."""
    if not value:
        return 1, 1
    try:
        parts = str(value).strip().split('/')
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
    except (ValueError, IndexError):
        return 1, 1


def _parse_date(value, override=None):
    """Return override date if given, else parse value from Excel."""
    if override:
        return override
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.today()


def _get_or_create_destination(name, prefix=None):
    """
    Find a Destination by prefix (preferred) or by name substring.
    Creates one if not found and prefix is provided.
    """
    if prefix:
        dest = Destination.objects.filter(prefix=str(prefix)).first()
        if dest:
            return dest, False
        # Create new destination
        dest = Destination.objects.create(
            name=name.title(),
            prefix=str(prefix),
            is_active=True,
        )
        return dest, True
    # Fallback: search by name
    dest = Destination.objects.filter(name__iexact=name).first()
    if not dest:
        dest = Destination.objects.filter(name__icontains=name).first()
    return dest, False


class Command(BaseCommand):
    help = 'Import a vendor rate notification Excel (4-sheet format) into a tariff.'

    def add_arguments(self, parser):
        parser.add_argument('xlsx_file', help='Path to the rate notification Excel file.')
        parser.add_argument('--tariff', type=int, required=True,
                            help='Tariff ID to import rates into.')
        parser.add_argument('--effective', default=None,
                            help='Override effective date (YYYY-MM-DD). Uses file date if omitted.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Parse without writing anything.')
        parser.add_argument('--skip-standard', action='store_true',
                            help='Skip the standard A-Z rates sheet.')
        parser.add_argument('--skip-origin', action='store_true',
                            help='Skip the origin-based rates sheets.')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl is required: pip install openpyxl --break-system-packages')

        xlsx_path    = options['xlsx_file']
        tariff_id    = options['tariff']
        dry_run      = options['dry_run']
        skip_std     = options['skip_standard']
        skip_origin  = options['skip_origin']

        effective_override = None
        if options['effective']:
            try:
                effective_override = datetime.date.fromisoformat(options['effective'])
            except ValueError:
                raise CommandError(f"Invalid date: {options['effective']} — use YYYY-MM-DD.")

        try:
            tariff = Tariff.objects.get(pk=tariff_id)
        except Tariff.DoesNotExist:
            raise CommandError(f'Tariff ID {tariff_id} not found.')

        self.stdout.write(f'Tariff: {tariff}')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing will be written.\n'))

        self.stdout.write('Loading workbook…')
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        sheets = {s.lower(): s for s in wb.sheetnames}
        self.stdout.write(f'Sheets: {list(wb.sheetnames)}')

        stats = {
            'destinations_created': 0,
            'dialcodes_updated': 0,
            'std_rates_created': 0,
            'std_rates_updated': 0,
            'origin_groups_created': 0,
            'origin_dialcodes_created': 0,
            'origin_rates_created': 0,
            'origin_rates_updated': 0,
            'skipped': 0,
        }

        with transaction.atomic():

            # ── Sheet 2: Dialcodes → update Destination prefixes ──────────────
            if 'dialcodes' in sheets and not skip_std:
                self._import_dialcodes(
                    wb[sheets['dialcodes']], effective_override, dry_run, stats
                )

            # ── Sheet 1: Standard A-Z Prices ──────────────────────────────────
            if 'prices' in sheets and not skip_std:
                self._import_standard_rates(
                    wb[sheets['prices']], tariff, effective_override, dry_run, stats
                )

            # ── Sheet 4: Origin Based Billing Dialcodes ───────────────────────
            if 'origin based billing dialcodes' in sheets and not skip_origin:
                self._import_origin_dialcodes(
                    wb[sheets['origin based billing dialcodes']],
                    effective_override, dry_run, stats
                )

            # ── Sheet 3: Origin Based Billing Prices ──────────────────────────
            if 'origin based billing prices' in sheets and not skip_origin:
                self._import_origin_rates(
                    wb[sheets['origin based billing prices']],
                    tariff, effective_override, dry_run, stats
                )

            if dry_run:
                transaction.set_rollback(True)

        wb.close()
        self._print_stats(stats)

    # ── Dialcodes ─────────────────────────────────────────────────────────────

    def _import_dialcodes(self, ws, effective_override, dry_run, stats):
        self.stdout.write('Reading Dialcodes sheet…')

        # Build full map: prefix → dest_name from the sheet (splitting comma lists)
        sheet_map = {}  # prefix → dest_title
        for row in ws.iter_rows(min_row=7, values_only=True):
            dest_name, dialcode = row[0], row[1]
            if not dest_name or not dialcode:
                continue
            dest_title = str(dest_name).title()
            for prefix in str(dialcode).split(','):
                prefix = prefix.strip()[:30]  # cap at field max_length
                if prefix:
                    sheet_map[prefix] = dest_title

        self.stdout.write(f'  {len(sheet_map):,} total prefixes parsed from sheet')

        # Load all existing prefixes in one query
        existing = {d.prefix: d for d in Destination.objects.filter(prefix__in=sheet_map.keys())}

        to_create = []
        to_update = []
        for prefix, dest_title in sheet_map.items():
            dest = existing.get(prefix)
            if dest:
                if dest.name.upper() != dest_title.upper():
                    dest.name = dest_title
                    to_update.append(dest)
            else:
                to_create.append(Destination(name=dest_title, prefix=prefix, is_active=True))

        if to_create:
            Destination.objects.bulk_create(to_create, ignore_conflicts=True)
            stats['destinations_created'] += len(to_create)
        if to_update:
            Destination.objects.bulk_update(to_update, ['name'], batch_size=500)
            stats['dialcodes_updated'] += len(to_update)

        self.stdout.write(f'  Created: {len(to_create):,}  Updated: {len(to_update):,}')

    # ── Standard A-Z Prices ───────────────────────────────────────────────────

    def _import_standard_rates(self, ws, tariff, effective_override, dry_run, stats):
        self.stdout.write('Reading standard Prices sheet…')
        # Reload destinations so newly created ones from Dialcodes sheet are included
        dest_by_name = {d.name.upper(): d for d in Destination.objects.all()}

        rate_rows = []
        for row in ws.iter_rows(min_row=7, values_only=True):
            dest_name, rate_val, billing, date_val, comment = (list(row) + [None] * 5)[:5]
            if not dest_name or rate_val is None:
                continue
            try:
                rate_decimal = Decimal(str(rate_val))
            except InvalidOperation:
                stats['skipped'] += 1
                continue

            effective = _parse_date(date_val, effective_override)
            min_sec, incr_sec = _parse_billing(billing)
            dest_name_upper = str(dest_name).upper().strip()
            dest = dest_by_name.get(dest_name_upper)

            if not dest:
                stats['skipped'] += 1
                continue

            rate_rows.append(Rate(
                tariff=tariff,
                destination=dest,
                prefix=dest.prefix,
                rate_per_minute=rate_decimal,
                minimum_duration_sec=min_sec,
                billing_increment_sec=incr_sec,
                effective_date=effective,
                origin_group=None,
            ))

        # Bulk upsert: update existing, create new
        existing_keys = set(
            Rate.objects.filter(tariff=tariff, origin_group=None)
            .values_list('prefix', 'effective_date')
        )
        to_create = [r for r in rate_rows if (r.prefix, r.effective_date) not in existing_keys]
        to_update = [r for r in rate_rows if (r.prefix, r.effective_date) in existing_keys]

        if to_create:
            Rate.objects.bulk_create(to_create, ignore_conflicts=True, batch_size=500)
            stats['std_rates_created'] += len(to_create)
        if to_update:
            Rate.objects.bulk_update(
                to_update, ['rate_per_minute', 'minimum_duration_sec', 'billing_increment_sec'],
                batch_size=500
            )
            stats['std_rates_updated'] += len(to_update)

        self.stdout.write(f'  Matched: {len(rate_rows):,}  Skipped: {stats["skipped"]}')

    # ── Origin Dialcodes ──────────────────────────────────────────────────────

    def _import_origin_dialcodes(self, ws, effective_override, dry_run, stats):
        self.stdout.write('Reading Origin Based Billing Dialcodes sheet…')
        for row in ws.iter_rows(min_row=7, values_only=True):
            if not any(row):
                continue
            group_name, ani_prefix, date_val = row[0], row[1], row[2]
            if not group_name or not ani_prefix:
                continue

            group_name = str(group_name).strip()
            prefix_str = str(ani_prefix).strip()
            effective  = _parse_date(date_val, effective_override)

            group, g_created = OriginGroup.objects.get_or_create(name=group_name)
            if g_created:
                stats['origin_groups_created'] += 1

            _, d_created = OriginDialcode.objects.get_or_create(
                group=group,
                prefix=prefix_str,
                defaults={'effective_date': effective},
            )
            if d_created:
                stats['origin_dialcodes_created'] += 1

    # ── Origin Based Prices ───────────────────────────────────────────────────

    def _import_origin_rates(self, ws, tariff, effective_override, dry_run, stats):
        self.stdout.write('Reading Origin Based Billing Prices sheet…')
        dest_by_name = {d.name.upper(): d for d in Destination.objects.all()}
        group_cache  = {g.name: g for g in OriginGroup.objects.all()}

        rate_rows = []  # list of Rate objects to bulk-create/update
        for row in ws.iter_rows(min_row=7, values_only=True):
            if not any(row):
                continue
            orig_dest_name, main_dest_name, group_name, rate_val, date_val, billing, comment = \
                (list(row) + [None] * 7)[:7]

            if not main_dest_name or rate_val is None or not group_name:
                stats['skipped'] += 1
                continue

            try:
                rate_decimal = Decimal(str(rate_val))
            except InvalidOperation:
                stats['skipped'] += 1
                continue

            effective     = _parse_date(date_val, effective_override)
            min_sec, incr_sec = _parse_billing(billing)
            group_name    = str(group_name).strip()
            dest          = dest_by_name.get(str(main_dest_name).upper().strip())

            if not dest:
                stats['skipped'] += 1
                continue

            if group_name not in group_cache:
                group_cache[group_name], _ = OriginGroup.objects.get_or_create(name=group_name)
            group = group_cache[group_name]

            rate_rows.append(Rate(
                tariff=tariff,
                destination=dest,
                prefix=dest.prefix,
                rate_per_minute=rate_decimal,
                minimum_duration_sec=min_sec,
                billing_increment_sec=incr_sec,
                effective_date=effective,
                origin_group=group,
            ))

        existing_keys = set(
            Rate.objects.filter(tariff=tariff, origin_group__isnull=False)
            .values_list('prefix', 'effective_date', 'origin_group_id')
        )
        to_create = [r for r in rate_rows
                     if (r.prefix, r.effective_date, r.origin_group_id) not in existing_keys]
        to_update = [r for r in rate_rows
                     if (r.prefix, r.effective_date, r.origin_group_id) in existing_keys]

        if to_create:
            Rate.objects.bulk_create(to_create, ignore_conflicts=True, batch_size=500)
            stats['origin_rates_created'] += len(to_create)
        if to_update:
            Rate.objects.bulk_update(
                to_update, ['rate_per_minute', 'minimum_duration_sec', 'billing_increment_sec'],
                batch_size=500
            )
            stats['origin_rates_updated'] += len(to_update)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def _print_stats(self, stats):
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Import complete:'))
        self.stdout.write(f"  Destinations created:      {stats['destinations_created']}")
        self.stdout.write(f"  Dialcodes updated:         {stats['dialcodes_updated']}")
        self.stdout.write(f"  Standard rates created:    {stats['std_rates_created']}")
        self.stdout.write(f"  Standard rates updated:    {stats['std_rates_updated']}")
        self.stdout.write(f"  Origin groups created:     {stats['origin_groups_created']}")
        self.stdout.write(f"  Origin dialcodes created:  {stats['origin_dialcodes_created']}")
        self.stdout.write(f"  Origin rates created:      {stats['origin_rates_created']}")
        self.stdout.write(f"  Origin rates updated:      {stats['origin_rates_updated']}")
        if stats['skipped']:
            self.stdout.write(self.style.WARNING(f"  Skipped (no dest match):   {stats['skipped']}"))
