"""
assign_ddi_customers
====================
Parses company names out of DDINumber.notes (put there by import_ddi_numbers),
creates or finds matching Company records, then sets DDINumber.customer FK.

Run once after import_ddi_numbers:
  py manage.py assign_ddi_customers
  py manage.py assign_ddi_customers --dry-run
"""
import re
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Company
from apps.ddi.models import DDINumber


# ---------------------------------------------------------------------------
# Normalisation map  —  lower-cased key → canonical display name
# Merges known spelling variants / abbreviations into one Company record.
# ---------------------------------------------------------------------------
CANONICAL = {
    # Squaretalk variants
    'squaretalk':                   'Squaretalk',
    'squaretalk ':                  'Squaretalk',

    # Zoom variants
    'zoom call centre':             'Zoom Call Centre',
    'zoomcallcentre':               'Zoom Call Centre',
    'zoom call center':             'Zoom Call Centre',
    'zoom telecom':                 'Zoom Call Centre',

    # Toll Free Forwarding
    'tollfreeforwarding':           'TollFreeForwarding',
    'toll free forwarding':         'TollFreeForwarding',

    # VirtualCall
    'virtualcall':                  'VirtualCall',
    'virtual call':                 'VirtualCall',
    'virtual-call':                 'VirtualCall',

    # BitCall
    'bitcall':                      'BitCall',

    # SmartED
    'smarted':                      'SmartED',

    # CommPeak
    'commpeak':                     'CommPeak',

    # SuissUniverse
    'suissuniverse':                'SuissUniverse',
    'suissunivers':                 'SuissUniverse',
    'swiss universe':               'SuissUniverse',

    # Tech Services
    'tech services':                'Tech Services',
    'tech service':                 'Tech Services',

    # NetSwiss
    'netswiss':                     'NetSwiss',
    'netswiss telecom':             'NetSwiss',

    # Omega Telecom
    'omega telecom':                'Omega Telecom',

    # Infinity
    'infinity telecom':             'Infinity Telecom',
    'infinity':                     'Infinity Telecom',

    # DCI Telecom
    'dci telecom':                  'DCI Telecom',
}


def _normalise(raw_name: str) -> str:
    """Return canonical company name, or the cleaned original if not in map."""
    key = raw_name.strip().lower()
    return CANONICAL.get(key, raw_name.strip())


def _extract_company(notes: str):
    """
    Pull company name from a notes string like:
      'Area: 021 | Status: Taken (Comnica)'
      'Area: 044 | Status: Cancelled (Omega Telecom) 26.05.2025.'
    Returns None for free/unassigned numbers.
    """
    # Only look in the Status segment
    status_match = re.search(r'Status:\s*(.+?)(?:\s*\|.*)?$', notes)
    if not status_match:
        return None
    status = status_match.group(1).strip()

    # Must start with Taken / Blocked  (Cancelled = returned, treat as unassigned)
    if not re.match(r'^(Taken|Blocked)', status, re.IGNORECASE):
        return None

    # Extract name in parentheses
    paren = re.search(r'\(([^)]+)\)', status)
    if not paren:
        return None

    name = paren.group(1).strip().rstrip('.')
    # Exclude noise like "SquareTalk) - BLOCKED" — already handled by regex
    return name if name else None


def _short_code(name: str) -> str:
    """Generate a unique-ish short code from the company name."""
    code = re.sub(r'[^A-Za-z0-9]', '', name).upper()[:20]
    return code or name[:20].upper()


class Command(BaseCommand):
    help = 'Create Company records from DDI notes and assign DDINumber.customer FK.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would happen without writing anything.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be saved.\n'))

        # ── Pass 1: collect all canonical company names from DDINumber notes ──
        self.stdout.write('Scanning DDI notes for company names...')
        company_counts = {}
        numbers_to_update = []

        for num in DDINumber.objects.only('id', 'notes', 'customer_id').iterator(chunk_size=5000):
            raw = _extract_company(num.notes or '')
            if not raw:
                continue
            canonical = _normalise(raw)
            company_counts[canonical] = company_counts.get(canonical, 0) + 1
            numbers_to_update.append((num.id, canonical))

        self.stdout.write(f'  Found {len(company_counts)} unique companies across '
                          f'{len(numbers_to_update):,} assigned numbers.\n')

        for name, count in sorted(company_counts.items(), key=lambda x: -x[1]):
            self.stdout.write(f'  {count:>6,}  {name}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run complete — nothing written.'))
            return

        # ── Pass 2: create or fetch Company records ────────────────────────────
        self.stdout.write('\nCreating / fetching Company records...')
        company_map = {}  # canonical name → Company instance

        for name in company_counts:
            short = _short_code(name)
            # Ensure short_code uniqueness by appending a counter if needed
            base = short
            counter = 1
            while Company.objects.filter(short_code=short).exclude(
                name=name
            ).exists():
                short = f'{base[:18]}{counter:02d}'
                counter += 1

            company, created = Company.objects.get_or_create(
                name=name,
                defaults={
                    'short_code': short,
                    'role': Company.ROLE_CUSTOMER,
                    'is_active': True,
                    'notes': 'Auto-created from DDI import.',
                }
            )
            company_map[name] = company
            action = 'Created' if created else 'Found  '
            self.stdout.write(f'  {action}  {name}  [{company.short_code}]')

        # ── Pass 3: bulk-update DDINumber.customer ─────────────────────────────
        self.stdout.write(f'\nLinking {len(numbers_to_update):,} DDI numbers to companies...')

        BATCH = 2000
        updated = 0
        with transaction.atomic():
            for i in range(0, len(numbers_to_update), BATCH):
                chunk = numbers_to_update[i:i + BATCH]
                for num_id, canonical in chunk:
                    company = company_map.get(canonical)
                    if company:
                        DDINumber.objects.filter(pk=num_id).update(customer=company)
                        updated += 1
                if (i // BATCH) % 10 == 0:
                    self.stdout.write(f'  ...{i + len(chunk):,} processed')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone — {len(company_map)} companies, {updated:,} DDI numbers linked.'
        ))
