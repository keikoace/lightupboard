"""
import_ddi_numbers — Bulk-load DDI/DID inventory from the Lightup ranges Excel file.

Column mapping
--------------
  B  DID number         → DDINumber.number  (float → string, e.g. "41217000000")
  C  Taken/Free         → DDINumber.notes (stored verbatim) + status derivation
  D  Golden or standard → appended to notes; also triggers is_active=False if blocked

Status rules
------------
  Taken/Free is None or blank   → available inventory, is_active=True
  Taken/Free starts with 'Taken'→ assigned, is_active=True
  Taken/Free starts with 'Cancelled' or 'Released' → returned, is_active=True
  'Blocked' anywhere in either column → is_active=False

Each sheet is named after the area code (e.g. '021'). That is stored in notes too.

Usage
-----
  py manage.py import_ddi_numbers
  py manage.py import_ddi_numbers "C:\\path\\to\\file.xlsx"
  py manage.py import_ddi_numbers --skip-existing   (default: update existing records)
  py manage.py import_ddi_numbers --dry-run
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ddi.models import DDINumber

DEFAULT_PATH = os.path.join(
    os.path.expanduser('~'),
    'Downloads',
    'INTERNAL_DIDs Lightup ranges.xlsx',
)

BLOCKED_KEYWORDS = ('blocked', 'block')


def _is_blocked(taken_val, golden_val):
    taken = (taken_val or '').lower()
    golden = (golden_val or '').lower()
    return any(k in taken for k in BLOCKED_KEYWORDS) or any(k in golden for k in BLOCKED_KEYWORDS)


def _parse_number(raw):
    """Convert float 41217000000.0 → '41217000000', or return None on bad data."""
    if raw is None:
        return None
    try:
        return str(int(float(raw)))
    except (ValueError, TypeError):
        return None


def _build_notes(area_code, taken_val, golden_val):
    parts = [f'Area: {area_code}']
    if taken_val and str(taken_val).strip():
        parts.append(f'Status: {str(taken_val).strip()}')
    gv = (golden_val or '').strip()
    if gv and gv.upper() not in ('GOLDEN', 'STANDARD', ''):
        # Only include if it has extra info (e.g. blocked reason)
        parts.append(f'Type note: {gv}')
    elif gv.upper() == 'GOLDEN':
        parts.append('Type: Golden')
    return ' | '.join(parts)


class Command(BaseCommand):
    help = 'Bulk-import DDI/DID numbers from the Lightup ranges Excel file.'

    def add_arguments(self, parser):
        parser.add_argument(
            'xlsx_file', nargs='?', default=DEFAULT_PATH,
            help=f'Path to the Excel file (default: {DEFAULT_PATH})',
        )
        parser.add_argument(
            '--skip-existing', action='store_true',
            help='Skip numbers that already exist (default: update notes/status).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Parse and count records without writing to the database.',
        )
        parser.add_argument(
            '--batch', type=int, default=1000,
            help='Bulk-create batch size (default: 1000).',
        )

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl is required. Run: pip install openpyxl --break-system-packages')

        xlsx_path = options['xlsx_file']
        skip_existing = options['skip_existing']
        dry_run = options['dry_run']
        batch_size = options['batch']

        if not os.path.exists(xlsx_path):
            raise CommandError(
                f'File not found: {xlsx_path}\n'
                'Pass the path explicitly: py manage.py import_ddi_numbers "C:\\path\\to\\file.xlsx"'
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing will be written.\n'))

        self.stdout.write(f'Loading workbook: {xlsx_path}')
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)

        # Pre-load existing numbers for fast dedup lookup
        self.stdout.write('Loading existing DDI numbers from database...')
        existing = set(DDINumber.objects.values_list('number', flat=True))
        self.stdout.write(f'  {len(existing):,} already in DB.\n')

        total_parsed = 0
        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_blocked = 0

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            area_code = sheet_name.split()[0]  # handle "058 - Nomadic" → "058"

            to_create = []
            to_update = []  # list of (number_str, notes, is_active)

            for row in ws.iter_rows(min_row=2, values_only=True):
                raw_num = row[1]   # column B
                taken_val = row[2]  # column C
                golden_val = row[3]  # column D

                number = _parse_number(raw_num)
                if not number:
                    continue

                total_parsed += 1
                blocked = _is_blocked(taken_val, golden_val)
                if blocked:
                    total_blocked += 1

                notes = _build_notes(area_code, taken_val, golden_val)
                is_active = not blocked

                if number in existing:
                    if skip_existing:
                        total_skipped += 1
                        continue
                    to_update.append((number, notes, is_active))
                else:
                    to_create.append(DDINumber(
                        number=number,
                        is_active=is_active,
                        notes=notes,
                    ))
                    existing.add(number)  # prevent intra-file dupes

            if not dry_run:
                # Bulk create
                for i in range(0, len(to_create), batch_size):
                    chunk = to_create[i:i + batch_size]
                    DDINumber.objects.bulk_create(chunk, ignore_conflicts=True)
                total_created += len(to_create)

                # Update existing
                for number, notes, is_active in to_update:
                    DDINumber.objects.filter(number=number).update(notes=notes, is_active=is_active)
                total_updated += len(to_update)
            else:
                total_created += len(to_create)
                total_updated += len(to_update)

            self.stdout.write(
                f'  Sheet {sheet_name:20s}: {len(to_create):>6,} new, '
                f'{len(to_update):>5,} update, {sum(1 for _, _, a in to_update if not a) + sum(1 for d in to_create if not d.is_active):>5,} blocked'
            )

        wb.close()

        suffix = ' (DRY RUN)' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'\nDone{suffix} — '
            f'parsed: {total_parsed:,}, '
            f'created: {total_created:,}, '
            f'updated: {total_updated:,}, '
            f'skipped: {total_skipped:,}, '
            f'blocked: {total_blocked:,}'
        ))
