"""
Management command: fetch_exchange_rates
Fetches USD and CHF rates from the European Central Bank (ECB) daily XML feed.
Run daily via Windows Task Scheduler:
    py manage.py fetch_exchange_rates

ECB publishes rates each working day by ~16:00 CET.
On weekends / bank holidays the previous working-day rates are returned.
"""
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

try:
    import certifi
    _CERTIFI_CAFILE = certifi.where()
except ImportError:
    _CERTIFI_CAFILE = None

from django.core.management.base import BaseCommand, CommandError

from apps.finance.models import ExchangeRate

ECB_URL = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'
CURRENCIES_WANTED = {'USD', 'CHF'}

# ECB XML namespaces
NS = {
    'gesmes': 'http://www.gesmes.org/xml/2002-08-01',
    'ecb':    'http://www.ecb.int/vocabulary/2002-08-01/eurofxref',
}


class Command(BaseCommand):
    help = 'Fetch today\'s EUR/USD and EUR/CHF rates from the ECB and store them.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-fetch and overwrite even if today\'s rates already exist.',
        )

    def handle(self, *args, **options):
        force = options['force']

        # ── 1. Download ECB XML ─────────────────────────────────────────
        self.stdout.write('Fetching ECB exchange rates…')

        # Build SSL contexts to try in order:
        # 1. System CA store  2. certifi bundle  3. No verification (proxy/SSL-inspection fallback)
        def _contexts():
            yield 'system CA', ssl.create_default_context()
            if _CERTIFI_CAFILE:
                ctx = ssl.create_default_context(cafile=_CERTIFI_CAFILE)
                yield 'certifi', ctx
            yield 'unverified', ssl._create_unverified_context()

        xml_data = None
        last_exc = None
        for label, ctx in _contexts():
            try:
                with urllib.request.urlopen(ECB_URL, timeout=15, context=ctx) as resp:
                    xml_data = resp.read()
                if label == 'unverified':
                    self.stdout.write(
                        self.style.WARNING(
                            '  ⚠ SSL certificate chain not trusted (corporate proxy?). '
                            'Fetched without verification — connection is still encrypted.'
                        )
                    )
                else:
                    self.stdout.write(f'  SSL OK ({label})')
                break
            except urllib.error.URLError as exc:
                # URLError wraps ssl.SSLError for certificate failures
                reason = exc.reason
                is_ssl = isinstance(reason, ssl.SSLError) or (
                    hasattr(reason, 'args') and any('SSL' in str(a) for a in reason.args)
                )
                if is_ssl and label != 'unverified':
                    self.stdout.write(f'  SSL failed with {label} — trying next…')
                    last_exc = exc
                else:
                    raise CommandError(f'Failed to fetch ECB data: {exc}')
            except Exception as exc:
                raise CommandError(f'Failed to fetch ECB data: {exc}')

        if not xml_data:
            raise CommandError(f'Failed to fetch ECB data after all SSL attempts: {last_exc}')

        # ── 2. Parse XML ────────────────────────────────────────────────
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as exc:
            raise CommandError(f'Failed to parse ECB XML: {exc}')

        # Structure: Envelope > Cube > Cube[time] > Cube[currency, rate]*
        outer_cube = root.find('ecb:Cube', NS)
        if outer_cube is None:
            raise CommandError('Unexpected ECB XML structure (no outer Cube).')

        time_cube = outer_cube.find('ecb:Cube', NS)
        if time_cube is None:
            raise CommandError('Unexpected ECB XML structure (no time Cube).')

        rate_date_str = time_cube.get('time')
        if not rate_date_str:
            raise CommandError('ECB XML missing date attribute.')

        rate_date = date.fromisoformat(rate_date_str)
        self.stdout.write(f'  ECB rates for: {rate_date}')

        parsed = {}
        for cube in time_cube.findall('ecb:Cube', NS):
            currency = cube.get('currency', '').upper()
            if currency in CURRENCIES_WANTED:
                try:
                    parsed[currency] = Decimal(cube.get('rate'))
                except Exception:
                    self.stderr.write(f'  Could not parse rate for {currency}')

        if not parsed:
            raise CommandError('No target currencies found in ECB XML.')

        # ── 3. Store in DB (upsert) ─────────────────────────────────────
        created_count = updated_count = skipped_count = 0

        for currency, rate in parsed.items():
            existing = ExchangeRate.objects.filter(
                date=rate_date, base_currency='EUR', currency=currency
            ).first()

            if existing and not force:
                self.stdout.write(f'  EUR/{currency} already stored — skipping (use --force to overwrite).')
                skipped_count += 1
                continue

            obj, created = ExchangeRate.objects.update_or_create(
                date=rate_date,
                base_currency='EUR',
                currency=currency,
                defaults={'rate': rate, 'source': 'ECB'},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'  Created  EUR/{currency} = {rate}'))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'  Updated  EUR/{currency} = {rate}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}.'
            )
        )
