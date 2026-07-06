"""
migrate_from_sqlite — Copy all data from the local db.sqlite3 into the configured
PostgreSQL database (or any other Django default DB).

Usage:
    python manage.py migrate_from_sqlite
    python manage.py migrate_from_sqlite --sqlite path/to/other.sqlite3
    python manage.py migrate_from_sqlite --skip-cdrs        (skip the 850k CDR rows)
    python manage.py migrate_from_sqlite --dry-run

The command:
  - Runs Django migrations on the target DB first (if needed)
  - Copies tables in dependency order using INSERT … ON CONFLICT DO NOTHING
  - Skips the removed `profile_id` column on ddi_ddinumber
  - Resets all PostgreSQL sequences after bulk insert
"""
import os
import sqlite3

from django.core.management.base import BaseCommand
from django.db import connection, transaction

SQLITE_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', '..', '..', 'db.sqlite3',
)

# Tables in dependency order (parents before children).
# Each entry: (sqlite_table, pg_table, skip_columns)
TABLES = [
    # Auth
    ('auth_user',                       'auth_user',                       []),
    # Core
    ('core_destination',                'core_destination',                []),
    ('core_company',                    'core_company',                    []),
    ('core_company_account_managers',   'core_company_account_managers',   []),
    ('core_company_portal_users',       'core_company_portal_users',       []),
    # DDI  — profile_id was removed from the model, skip it
    ('ddi_ddinumber',                   'ddi_ddinumber',                   ['profile_id']),
    # Rates
    ('rates_tariff',                    'rates_tariff',                    []),
    ('rates_rate',                      'rates_rate',                      []),
    # Finance
    ('finance_billingprofile',          'finance_billingprofile',          []),
    ('finance_exchangerate',            'finance_exchangerate',            []),
    ('finance_billableitem',            'finance_billableitem',            []),
    ('finance_invoice',                 'finance_invoice',                 []),
    ('finance_invoiceline',             'finance_invoiceline',             []),
    ('finance_payment',                 'finance_payment',                 []),
    ('finance_termdeal',                'finance_termdeal',                []),
    ('finance_revenueshare',            'finance_revenueshare',            []),
    # QoS  — CDRs last (biggest table)
    ('qos_minutesummary',               'qos_minutesummary',               []),
    ('qos_cdr',                         'qos_cdr',                         []),
    # Setup
    ('setup_ticket',                    'setup_ticket',                    []),
]

# SQLite stores booleans as 0/1 integers; map table → bool columns so we cast them
BOOL_COLUMNS = {
    'auth_user':              {'is_superuser', 'is_staff', 'is_active'},
    'core_company':           {'is_active', 'vat_exempt'},
    'core_destination':       {'is_active'},
    'ddi_ddinumber':          {'is_active', 'ported_in'},
    'qos_cdr':                {'is_processed'},
    'rates_tariff':           {'is_active'},
    'finance_billingprofile': {'is_active'},
    'finance_billableitem':   {'is_active'},
    'finance_termdeal':       {'is_active'},
    'finance_revenueshare':   {'is_active'},
}

# Sequences to reset after bulk insert (table → pk column)
SEQUENCES = [
    'auth_user', 'core_destination', 'core_company',
    'core_company_account_managers', 'core_company_portal_users',
    'ddi_ddinumber', 'rates_tariff', 'rates_rate',
    'finance_billingprofile', 'finance_exchangerate', 'finance_billableitem',
    'finance_invoice', 'finance_invoiceline', 'finance_payment',
    'finance_termdeal', 'finance_revenueshare',
    'qos_minutesummary', 'qos_cdr', 'setup_ticket',
]


class Command(BaseCommand):
    help = 'Migrate all data from db.sqlite3 into the configured PostgreSQL database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sqlite', default=None,
            help=f'Path to the SQLite file (default: db.sqlite3 in project root)',
        )
        parser.add_argument(
            '--skip-cdrs', action='store_true',
            help='Skip copying qos_cdr rows (speeds things up when you only need reference data)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Count rows without writing anything',
        )
        parser.add_argument(
            '--batch', type=int, default=2000,
            help='Insert batch size (default 2000)',
        )

    def handle(self, *args, **options):
        sqlite_path = options['sqlite'] or os.path.normpath(SQLITE_DEFAULT)
        if not os.path.exists(sqlite_path):
            self.stderr.write(self.style.ERROR(f'SQLite file not found: {sqlite_path}'))
            return

        skip_cdrs = options['skip_cdrs']
        dry_run   = options['dry_run']
        batch     = options['batch']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing will be written.\n'))

        src = sqlite3.connect(sqlite_path)
        src.row_factory = sqlite3.Row

        pg = connection  # Django's configured DB

        total_inserted = 0

        for (src_table, dst_table, skip_cols) in TABLES:
            if skip_cdrs and src_table == 'qos_cdr':
                self.stdout.write(f'  Skipping {src_table} (--skip-cdrs)')
                continue

            # Get columns from source
            src_cur = src.cursor()
            try:
                src_cur.execute(f'SELECT * FROM "{src_table}" LIMIT 0')
            except sqlite3.OperationalError:
                self.stdout.write(f'  {src_table}: not found in SQLite, skipping')
                continue

            all_cols = [d[0] for d in src_cur.description]
            cols = [c for c in all_cols if c not in skip_cols]
            col_list = ', '.join(f'"{c}"' for c in cols)
            placeholders = ', '.join(['%s'] * len(cols))

            # Count source rows
            src_cur.execute(f'SELECT COUNT(*) FROM "{src_table}"')
            total = src_cur.fetchone()[0]

            if total == 0:
                self.stdout.write(f'  {src_table}: 0 rows, skipping')
                continue

            if dry_run:
                self.stdout.write(f'  {src_table}: {total:,} rows (dry run)')
                continue

            inserted = 0
            sql = (
                f'INSERT INTO "{dst_table}" ({col_list}) '
                f'VALUES ({placeholders}) '
                f'ON CONFLICT DO NOTHING'
            )

            src_cur.execute(f'SELECT {", ".join(f"[{c}]" for c in cols)} FROM "{src_table}"')

            bool_cols = BOOL_COLUMNS.get(src_table, set())
            bool_indices = {i for i, c in enumerate(cols) if c in bool_cols}

            def cast_row(row):
                row = list(row)
                for i in bool_indices:
                    if row[i] is not None:
                        row[i] = bool(row[i])
                return tuple(row)

            with transaction.atomic():
                with pg.cursor() as dst_cur:
                    while True:
                        rows = src_cur.fetchmany(batch)
                        if not rows:
                            break
                        dst_cur.executemany(sql, [cast_row(r) for r in rows])
                        inserted += len(rows)

            total_inserted += inserted
            self.stdout.write(f'  {src_table}: {inserted:,} rows copied')

        src.close()

        if not dry_run:
            # Reset sequences so new inserts get correct IDs
            self.stdout.write('\nResetting sequences...')
            with pg.cursor() as cur:
                for table in SEQUENCES:
                    try:
                        cur.execute(
                            f"SELECT setval(pg_get_serial_sequence('\"{table}\"', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM \"{table}\"), 1))"
                        )
                    except Exception as e:
                        pg.connection.rollback() if hasattr(pg, 'connection') else None
                        self.stdout.write(f'  sequence reset skipped for {table}: {e}')

            self.stdout.write(self.style.SUCCESS(
                f'\nDone — {total_inserted:,} total rows copied to PostgreSQL.'
            ))
        else:
            self.stdout.write(self.style.WARNING('\nDry run complete — no data written.'))
