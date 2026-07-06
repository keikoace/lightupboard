"""
fix_ddi_assignments — Re-apply customer/vendor assignments to DDINumber rows
by matching company names from SQLite → PostgreSQL.

Use this when the migration copied DID numbers but left customer_id/vendor_id
as NULL because company IDs differ between the two databases.

Usage:
    python manage.py fix_ddi_assignments
    python manage.py fix_ddi_assignments --sqlite path/to/db.sqlite3
    python manage.py fix_ddi_assignments --dry-run
"""
import os
import sqlite3

from django.core.management.base import BaseCommand
from django.db import transaction

SQLITE_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', '..', '..', 'db.sqlite3',
)


class Command(BaseCommand):
    help = 'Re-apply DID customer/vendor assignments from SQLite using name-based company matching.'

    def add_arguments(self, parser):
        parser.add_argument('--sqlite', default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        from apps.ddi.models import DDINumber
        from apps.core.models import Company

        sqlite_path = options['sqlite'] or os.path.normpath(SQLITE_DEFAULT)
        dry_run = options['dry_run']

        if not os.path.exists(sqlite_path):
            self.stderr.write(f'SQLite file not found: {sqlite_path}')
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing will be written.\n'))

        # ── Build name → PK map from PostgreSQL companies ─────────────────────
        pg_companies = {c.name: c.pk for c in Company.objects.all()}
        self.stdout.write(f'PostgreSQL companies loaded: {len(pg_companies)}')

        # ── Read SQLite: number → (customer_name, vendor_name) ────────────────
        src = sqlite3.connect(sqlite_path)
        cur = src.cursor()
        cur.execute("""
            SELECT d.number,
                   cust.name  AS customer_name,
                   vend.name  AS vendor_name
            FROM ddi_ddinumber d
            LEFT JOIN core_company cust ON cust.id = d.customer_id
            LEFT JOIN core_company vend ON vend.id = d.vendor_id
            WHERE d.customer_id IS NOT NULL OR d.vendor_id IS NOT NULL
        """)
        rows = cur.fetchall()
        src.close()
        self.stdout.write(f'SQLite rows with assignments: {len(rows):,}')

        # ── Apply to PostgreSQL ───────────────────────────────────────────────
        updated = skipped_no_company = skipped_no_number = 0
        batch = []

        for number, customer_name, vendor_name in rows:
            customer_id = pg_companies.get(customer_name) if customer_name else None
            vendor_id   = pg_companies.get(vendor_name)   if vendor_name   else None

            if customer_name and not customer_id:
                skipped_no_company += 1
                self.stdout.write(
                    self.style.WARNING(f'  Company not found in PG: "{customer_name}"')
                )
                continue

            batch.append((number, customer_id, vendor_id))

        self.stdout.write(f'Rows to update: {len(batch):,}  |  skipped (company missing): {skipped_no_company}')

        if dry_run or not batch:
            return

        # Bulk update in chunks
        CHUNK = 2000
        with transaction.atomic():
            for i in range(0, len(batch), CHUNK):
                chunk = batch[i:i + CHUNK]
                numbers = [r[0] for r in chunk]
                number_map = {r[0]: (r[1], r[2]) for r in chunk}

                ddi_objs = DDINumber.objects.filter(number__in=numbers)
                to_save = []
                for obj in ddi_objs:
                    cid, vid = number_map[obj.number]
                    obj.customer_id = cid
                    obj.vendor_id   = vid
                    to_save.append(obj)
                DDINumber.objects.bulk_update(to_save, ['customer_id', 'vendor_id'], batch_size=500)
                updated += len(to_save)
                self.stdout.write(f'  {updated:,} updated…')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone — {updated:,} DID numbers re-assigned.'
        ))
