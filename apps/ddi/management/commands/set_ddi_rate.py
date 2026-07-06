"""
set_ddi_rate — Bulk-set buy/sell rate on DDI numbers for a customer.

Usage
-----
  py manage.py set_ddi_rate "Squaretalk" --buy 2.20
  py manage.py set_ddi_rate "Zoom Call Centre" --sell 3.50
  py manage.py set_ddi_rate "Omega Telecom" --buy 1.80 --sell 2.50
  py manage.py set_ddi_rate "Squaretalk" --buy 2.20 --dry-run
"""
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from apps.core.models import Company
from apps.ddi.models import DDINumber


class Command(BaseCommand):
    help = 'Bulk-set buy/sell rate on all DDI numbers for a given customer.'

    def add_arguments(self, parser):
        parser.add_argument('customer', type=str,
                            help='Company name (or partial match) to update.')
        parser.add_argument('--buy', type=str, default=None,
                            help='Buy rate per number (e.g. 2.20).')
        parser.add_argument('--sell', type=str, default=None,
                            help='Sell rate per number (e.g. 3.50).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would change without saving.')

    def handle(self, *args, **options):
        name_query = options['customer']
        buy_str = options['buy']
        sell_str = options['sell']
        dry_run = options['dry_run']

        if not buy_str and not sell_str:
            raise CommandError('Specify at least --buy or --sell (or both).')

        # Parse rates
        buy_rate = sell_rate = None
        try:
            if buy_str:
                buy_rate = Decimal(buy_str)
            if sell_str:
                sell_rate = Decimal(sell_str)
        except InvalidOperation:
            raise CommandError('Invalid rate value — use a number like 2.20')

        # Find company (case-insensitive, partial match)
        companies = Company.objects.filter(name__icontains=name_query)
        if not companies.exists():
            raise CommandError(
                f'No company found matching "{name_query}".\n'
                'Run: py manage.py shell -c "from apps.core.models import Company; '
                '[print(c.name) for c in Company.objects.all()]"'
            )
        if companies.count() > 1:
            self.stdout.write(self.style.WARNING(
                f'Multiple companies match "{name_query}":'
            ))
            for c in companies:
                self.stdout.write(f'  [{c.pk}] {c.name}')
            raise CommandError('Be more specific — use the exact company name.')

        company = companies.first()
        qs = DDINumber.objects.filter(customer=company)
        count = qs.count()

        if count == 0:
            raise CommandError(f'No DDI numbers assigned to "{company.name}".')

        # Show what we're about to do
        changes = []
        if buy_rate is not None:
            changes.append(f'buy_rate → {buy_rate:.6f}')
        if sell_rate is not None:
            changes.append(f'sell_rate → {sell_rate:.6f}')

        self.stdout.write(
            f'{"[DRY RUN] " if dry_run else ""}'
            f'Updating {count:,} DDI numbers for {company.name}: '
            + ', '.join(changes)
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run — no changes saved.'))
            return

        update_kwargs = {}
        if buy_rate is not None:
            update_kwargs['buy_rate'] = buy_rate
        if sell_rate is not None:
            update_kwargs['sell_rate'] = sell_rate

        updated = qs.update(**update_kwargs)
        self.stdout.write(self.style.SUCCESS(f'Done — {updated:,} numbers updated.'))
