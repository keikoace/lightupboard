"""
Rating tests for the process_cdrs command.

These run against whichever database is configured, and are the guard against
the PostgreSQL fast path and the SQLite fallback drifting apart. Run them on
both engines after touching rating logic:

    python manage.py test apps.qos                        # configured engine
    DB_ENGINE=postgresql DB_PASSWORD=... python manage.py test apps.qos
"""
import datetime
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Company, Destination
from apps.qos.models import CDR
from apps.rates.models import Tariff, Rate, OriginGroup, OriginDialcode


EFFECTIVE = datetime.date(2020, 1, 1)


class BilledSecondsFormulaTests(TestCase):
    """The pure helper, independent of any database."""

    def test_billed_seconds(self):
        from apps.qos.management.commands.process_cdrs import _billed_seconds

        # (duration, minimum, increment) -> billed
        cases = [
            (0,   60, 6, 0),    # unanswered
            (1,   60, 6, 60),   # below the minimum bills the minimum
            (60,  60, 6, 60),   # exactly the minimum
            (61,  60, 6, 66),   # one second over rounds up a full increment
            (66,  60, 6, 66),   # exactly on an increment boundary
            (67,  60, 6, 72),
            (61,   1, 1, 61),   # per-second billing is a no-op
            (61,  30, 30, 90),
        ]
        for duration, minimum, increment, expected in cases:
            with self.subTest(duration=duration, billing=f'{minimum}/{increment}'):
                self.assertEqual(_billed_seconds(duration, minimum, increment), expected)


class ProcessCdrsRatingTests(TestCase):
    """
    End-to-end: seed tariffs + CDRs, run the command, assert what got billed.

    Every assertion here must hold identically on PostgreSQL and SQLite.
    """

    @classmethod
    def setUpTestData(cls):
        cls.customer = Company.objects.create(name='Test Customer', role=Company.ROLE_CUSTOMER)
        cls.supplier = Company.objects.create(name='Test Supplier', role=Company.ROLE_SUPPLIER)

        Destination.objects.create(name='Germany Fixed', prefix='49', is_active=True)

        # Sell side: 60/6 billing at 0.10/min
        cls.sell_tariff = Tariff.objects.create(
            company=cls.customer, name='Sell', side=Tariff.SIDE_SELL,
            effective_date=EFFECTIVE, is_active=True,
        )
        Rate.objects.create(
            tariff=cls.sell_tariff, destination=Destination.objects.get(prefix='49'),
            prefix='49', rate_per_minute=Decimal('0.100000'),
            minimum_duration_sec=60, billing_increment_sec=6, effective_date=EFFECTIVE,
        )

        # Origin-based sell rate: calls from ANI 1417* bill at 0.20/min, per-second
        cls.origin_group = OriginGroup.objects.create(name='AT-A')
        OriginDialcode.objects.create(group=cls.origin_group, prefix='1417', effective_date=EFFECTIVE)
        Rate.objects.create(
            tariff=cls.sell_tariff, destination=Destination.objects.get(prefix='49'),
            prefix='49', rate_per_minute=Decimal('0.200000'), origin_group=cls.origin_group,
            minimum_duration_sec=1, billing_increment_sec=1, effective_date=EFFECTIVE,
        )

        # Buy side: 30/30 billing at 0.05/min
        cls.buy_tariff = Tariff.objects.create(
            company=cls.supplier, name='Buy', side=Tariff.SIDE_BUY,
            effective_date=EFFECTIVE, is_active=True,
        )
        Rate.objects.create(
            tariff=cls.buy_tariff, destination=Destination.objects.get(prefix='49'),
            prefix='49', rate_per_minute=Decimal('0.050000'),
            minimum_duration_sec=30, billing_increment_sec=30, effective_date=EFFECTIVE,
        )

    def _cdr(self, *, switch_billed_sec, ani='9999999', answered=True, call_id='c1'):
        start = timezone.make_aware(datetime.datetime(2026, 5, 1, 10, 0, 0))
        return CDR.objects.create(
            call_id=call_id,
            customer=self.customer,
            supplier=self.supplier,
            ani=ani,
            dnis='4930123456',
            start_time=start,
            answer_time=start + datetime.timedelta(seconds=2) if answered else None,
            duration_sec=switch_billed_sec,
            switch_billed_sec=switch_billed_sec,
            is_processed=False,
        )

    def test_sell_and_buy_increments_are_applied(self):
        """61s under 60/6 sell and 30/30 buy must not bill as 61 raw seconds."""
        cdr = self._cdr(switch_billed_sec=61)
        call_command('process_cdrs', verbosity=0)
        cdr.refresh_from_db()

        # sell: 60 + ceil(1/6)*6 = 66s -> 66/60 * 0.10
        self.assertEqual(cdr.sell_billed_duration_sec, 66)
        self.assertEqual(cdr.sell_rate, Decimal('0.100000'))
        self.assertEqual(cdr.sell_revenue, Decimal('0.1100'))

        # buy: 30 + ceil(31/30)*30 = 90s -> 90/60 * 0.05
        self.assertEqual(cdr.buy_billed_duration_sec, 90)
        self.assertEqual(cdr.buy_rate, Decimal('0.050000'))
        self.assertEqual(cdr.buy_cost, Decimal('0.0750'))

        self.assertTrue(cdr.is_processed)
        self.assertEqual(cdr.destination.prefix, '49')

    def test_duration_below_minimum_bills_the_minimum(self):
        cdr = self._cdr(switch_billed_sec=5)
        call_command('process_cdrs', verbosity=0)
        cdr.refresh_from_db()

        self.assertEqual(cdr.sell_billed_duration_sec, 60)   # 60/6
        self.assertEqual(cdr.sell_revenue, Decimal('0.1000'))
        self.assertEqual(cdr.buy_billed_duration_sec, 30)    # 30/30
        self.assertEqual(cdr.buy_cost, Decimal('0.0250'))

    def test_unanswered_call_bills_nothing(self):
        cdr = self._cdr(switch_billed_sec=0, answered=False)
        call_command('process_cdrs', verbosity=0)
        cdr.refresh_from_db()

        self.assertEqual(cdr.sell_billed_duration_sec, 0)
        self.assertEqual(cdr.sell_revenue, Decimal('0'))
        self.assertEqual(cdr.buy_billed_duration_sec, 0)
        self.assertEqual(cdr.buy_cost, Decimal('0'))

    def test_origin_rate_takes_precedence_and_uses_its_own_increment(self):
        """ANI 1417* matches the origin group: 0.20/min, per-second billing."""
        cdr = self._cdr(switch_billed_sec=61, ani='1417555000')
        call_command('process_cdrs', verbosity=0)
        cdr.refresh_from_db()

        self.assertEqual(cdr.sell_rate, Decimal('0.200000'))
        self.assertEqual(cdr.sell_billed_duration_sec, 61)   # 1/1, not the 60/6 standard rate
        self.assertEqual(cdr.sell_revenue, Decimal('0.2033'))
