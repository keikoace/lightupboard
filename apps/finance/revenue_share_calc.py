"""
Revenue share calculation engine.

Rules (fixed globally):
  - AM manages a CUSTOMER company  → 20% of CDR profit + 20% of billable items
  - AM manages a SUPPLIER company  → 10% of CDR profit
  - AM manages BOTH sides          → 20% (customer) + 10% (supplier) = 30%

CDR profit is converted to EUR using ECB rates before applying the percentage,
so cross-currency routes are handled correctly.

Usage:
    from apps.finance.revenue_share_calc import calculate_am_share
    result = calculate_am_share(user, period_start, period_end)
"""
import datetime
from decimal import Decimal

from django.db.models import Q, Sum, Count, F, Value
from django.db.models.functions import Coalesce

CUSTOMER_RATE = Decimal('0.20')   # 20%
SUPPLIER_RATE = Decimal('0.10')   # 10%

DISPLAY_CURRENCY = 'EUR'          # all amounts normalised to EUR


def _to_eur(amount, from_currency, on_date=None):
    """Convert amount → EUR. Returns original amount if rate unavailable."""
    if not amount or from_currency == DISPLAY_CURRENCY:
        return Decimal(str(amount or 0))
    from .currency import convert
    converted = convert(amount, from_currency, DISPLAY_CURRENCY, on_date)
    return converted if converted is not None else Decimal(str(amount))


def calculate_am_share(user, period_start, period_end):
    """
    Calculate one AM's revenue share for a date range.

    Returns a dict:
    {
        'rows': [
            {
                'company': Company,
                'role': 'customer' | 'supplier' | 'both',
                'cdr_profit_eur': Decimal,   # profit in EUR
                'cdr_share_eur': Decimal,    # AM's share of CDR profit
                'cdr_rate': Decimal,         # 0.10, 0.20, or 0.30
                'billable_eur': Decimal,     # monthly billable items value in EUR
                'billable_share_eur': Decimal,
                'total_share_eur': Decimal,
                'minutes': float,
                'calls': int,
            },
            ...
        ],
        'totals': {
            'cdr_profit_eur': Decimal,
            'cdr_share_eur': Decimal,
            'billable_eur': Decimal,
            'billable_share_eur': Decimal,
            'total_share_eur': Decimal,
        },
        'display_currency': 'EUR',
        'fx_date': date | None,
    }
    """
    from apps.core.models import Company
    from apps.qos.models import CDR
    from apps.finance.models import BillableItem
    from .currency import latest_rates_date

    fx_date = latest_rates_date()

    # Companies this AM manages
    managed = Company.objects.filter(
        account_managers=user, is_active=True
    ).distinct()

    customer_ids = set(managed.filter(role__in=['customer', 'both']).values_list('pk', flat=True))
    supplier_ids = set(managed.filter(role__in=['supplier', 'both']).values_list('pk', flat=True))
    all_ids      = customer_ids | supplier_ids

    if not all_ids:
        return _empty_result(fx_date)

    # ── CDR aggregation ────────────────────────────────────────────────────────
    # Group CDRs by (customer_id, supplier_id) so we can correctly attribute
    # profit to the customer-AM side and supplier-AM side separately.

    cdr_qs = (
        CDR.objects
        .filter(
            start_time__date__gte=period_start,
            start_time__date__lt=period_end,
            sell_billed_duration_sec__gt=0,
        )
        .filter(
            # Only CDRs where this AM manages at least one side
            Q(customer_id__in=customer_ids) | Q(supplier_id__in=supplier_ids)
        )
        .select_related('customer', 'supplier')
        .values(
            'customer_id', 'customer__currency',
            'supplier_id', 'supplier__currency',
        )
        .annotate(
            total_sell=Coalesce(Sum('sell_revenue'), Value(Decimal('0'))),
            total_buy=Coalesce(Sum('buy_cost'),      Value(Decimal('0'))),
            total_seconds=Sum('sell_billed_duration_sec'),
            calls=Count('id'),
        )
    )

    # Per-company accumulators
    company_data = {}   # pk → {...}

    for row in cdr_qs:
        sell_eur = _to_eur(row['total_sell'], row['customer__currency'] or 'USD', fx_date)
        buy_eur  = _to_eur(row['total_buy'],  row['supplier__currency'] or 'USD', fx_date)
        profit_eur = sell_eur - buy_eur

        minutes = (row['total_seconds'] or 0) / 60
        calls   = row['calls'] or 0

        # Customer side
        cust_pk = row['customer_id']
        if cust_pk and cust_pk in customer_ids:
            d = _ensure(company_data, cust_pk, managed)
            d['role_set'].add('customer')
            d['cdr_customer_profit_eur'] += profit_eur
            d['minutes'] += minutes
            d['calls']   += calls

        # Supplier side
        supp_pk = row['supplier_id']
        if supp_pk and supp_pk in supplier_ids:
            d = _ensure(company_data, supp_pk, managed)
            d['role_set'].add('supplier')
            d['cdr_supplier_profit_eur'] += profit_eur
            # Don't double-count minutes/calls — they belong to the customer side

    # ── Billable items (customer companies only, 20%) ──────────────────────────
    billable_qs = (
        BillableItem.objects
        .filter(
            customer_id__in=customer_ids,
            is_active=True,
            billing_type=BillableItem.BILLING_MONTHLY,
        )
        .values('customer_id', 'customer__currency')
        .annotate(monthly_value=Sum(F('unit_price') * F('quantity')))
    )

    for row in billable_qs:
        cust_pk = row['customer_id']
        d = _ensure(company_data, cust_pk, managed)
        d['role_set'].add('customer')
        value_eur = _to_eur(row['monthly_value'], row['customer__currency'] or 'USD', fx_date)
        d['billable_eur'] += value_eur

    # ── Build output rows ──────────────────────────────────────────────────────
    rows = []
    totals = {
        'cdr_profit_eur':      Decimal('0'),
        'cdr_share_eur':       Decimal('0'),
        'billable_eur':        Decimal('0'),
        'billable_share_eur':  Decimal('0'),
        'total_share_eur':     Decimal('0'),
        'minutes':             0.0,
        'calls':               0,
    }

    for pk, d in sorted(company_data.items(), key=lambda x: x[1]['company'].name):
        role_set = d['role_set']
        role = 'both' if len(role_set) > 1 else list(role_set)[0] if role_set else 'customer'

        cust_profit = d['cdr_customer_profit_eur']
        supp_profit = d['cdr_supplier_profit_eur']
        cdr_profit  = cust_profit + supp_profit

        cdr_share = (
            cust_profit * CUSTOMER_RATE +
            supp_profit * SUPPLIER_RATE
        )

        # Effective CDR rate for display (weighted average, or show as split)
        cdr_rate = (
            CUSTOMER_RATE + SUPPLIER_RATE if role == 'both'
            else CUSTOMER_RATE if role == 'customer'
            else SUPPLIER_RATE
        )

        billable_eur   = d['billable_eur']
        billable_share = billable_eur * CUSTOMER_RATE if 'customer' in role_set else Decimal('0')
        total_share    = cdr_share + billable_share

        row = {
            'company':            d['company'],
            'role':               role,
            'cdr_profit_eur':     cdr_profit.quantize(Decimal('0.01')),
            'cdr_share_eur':      cdr_share.quantize(Decimal('0.01')),
            'cdr_rate':           cdr_rate,
            'cdr_customer_profit': cust_profit.quantize(Decimal('0.01')),
            'cdr_supplier_profit': supp_profit.quantize(Decimal('0.01')),
            'billable_eur':       billable_eur.quantize(Decimal('0.01')),
            'billable_share_eur': billable_share.quantize(Decimal('0.01')),
            'total_share_eur':    total_share.quantize(Decimal('0.01')),
            'minutes':            round(d['minutes'], 1),
            'calls':              d['calls'],
        }
        rows.append(row)

        totals['cdr_profit_eur']     += cdr_profit
        totals['cdr_share_eur']      += cdr_share
        totals['billable_eur']       += billable_eur
        totals['billable_share_eur'] += billable_share
        totals['total_share_eur']    += total_share
        totals['minutes']            += d['minutes']
        totals['calls']              += d['calls']

    # Quantize totals
    for k in ('cdr_profit_eur', 'cdr_share_eur', 'billable_eur', 'billable_share_eur', 'total_share_eur'):
        totals[k] = totals[k].quantize(Decimal('0.01'))
    totals['minutes'] = round(totals['minutes'], 1)

    return {
        'rows':             rows,
        'totals':           totals,
        'display_currency': DISPLAY_CURRENCY,
        'fx_date':          fx_date,
    }


def _ensure(company_data, pk, managed_qs):
    if pk not in company_data:
        try:
            company = managed_qs.get(pk=pk)
        except Exception:
            from apps.core.models import Company
            company = Company.objects.get(pk=pk)
        company_data[pk] = {
            'company':                company,
            'role_set':               set(),
            'cdr_customer_profit_eur': Decimal('0'),
            'cdr_supplier_profit_eur': Decimal('0'),
            'billable_eur':           Decimal('0'),
            'minutes':                0.0,
            'calls':                  0,
        }
    return company_data[pk]


def _empty_result(fx_date):
    zero = Decimal('0')
    return {
        'rows': [],
        'totals': {
            'cdr_profit_eur': zero, 'cdr_share_eur': zero,
            'billable_eur':   zero, 'billable_share_eur': zero,
            'total_share_eur': zero, 'minutes': 0.0, 'calls': 0,
        },
        'display_currency': DISPLAY_CURRENCY,
        'fx_date': fx_date,
    }
