"""
assign_invoice_groups — Auto-tag Destination.invoice_group for invoice line grouping.

Logic:
  - Detects country and type (Fixed / Mobile) from destination name.
  - Fixed:  always "Country Fixed" regardless of sub-region.
  - Mobile: "Country Mobile OperatorName" if an operator is present after "Mobile",
            otherwise "Country Mobile Other".

Supported countries (add more to COUNTRIES as needed):
  Austria, Germany, Switzerland, Sweden

Usage:
    python manage.py assign_invoice_groups            # apply
    python manage.py assign_invoice_groups --dry-run  # preview
    python manage.py assign_invoice_groups --clear    # reset all groups
"""
import re
from django.core.management.base import BaseCommand
from apps.core.models import Destination

# Add / remove countries here as needed (matched case-insensitively)
COUNTRIES = [
    'Austria',
    'Germany',
    'Switzerland',
    'Sweden',
]

# Words to strip from the operator portion — noise from destination names
OPERATOR_STRIP = re.compile(
    r'\b(termination|term|international|intl|geographic|geographic|national|nat|'
    r'special|service|services|numbers?|calls?|voip|sip)\b',
    re.IGNORECASE,
)


def _parse(name: str) -> str:
    """Return invoice_group string for a destination name, or '' if no match."""
    name_lower = name.lower()

    # 1. Detect country
    country = None
    for c in COUNTRIES:
        if c.lower() in name_lower:
            country = c
            break
    if not country:
        return ''

    # 2. Detect type
    if 'mobile' in name_lower:
        # Extract everything after the word "mobile"
        m = re.search(r'mobile\s*(.*)', name, re.IGNORECASE)
        operator = m.group(1).strip() if m else ''
        # Strip noise words and clean up
        operator = OPERATOR_STRIP.sub('', operator).strip(' -–—/')
        operator = re.sub(r'\s+', ' ', operator).strip()
        if operator:
            return f'{country} Mobile {operator}'
        return f'{country} Mobile Other'
    else:
        # Fixed (includes "Fixed", "Geographic", plain country, city names, etc.)
        return f'{country} Fixed'


class Command(BaseCommand):
    help = 'Auto-assign Destination.invoice_group based on name parsing.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Preview changes without writing.')
        parser.add_argument('--clear', action='store_true',
                            help='Remove all invoice_group values.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clear   = options['clear']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no writes.\n'))

        destinations = Destination.objects.all().order_by('name')
        changed = []

        for dest in destinations:
            new_group = '' if clear else _parse(dest.name)
            if dest.invoice_group != new_group:
                old = dest.invoice_group or '(none)'
                new = new_group          or '(none)'
                self.stdout.write(f'  {dest.name[:55]:<55}  {old} → {new}')
                dest.invoice_group = new_group
                changed.append(dest)

        self.stdout.write(f'\n{len(changed)} destination(s) {"would change" if dry_run else "to update"}.')

        if changed and not dry_run:
            Destination.objects.bulk_update(changed, ['invoice_group'], batch_size=500)
            self.stdout.write(self.style.SUCCESS('Done.'))
        elif not changed:
            self.stdout.write('Nothing to change.')
