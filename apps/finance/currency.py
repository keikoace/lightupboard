"""
Currency conversion utilities for the Finance module.

All rates are stored with EUR as base (source: ECB).
Cross-rates are derived via EUR:  A→B = (rate_B / rate_A)
EUR itself has an implied rate of 1.0.
"""
from decimal import Decimal
from datetime import date as date_type

from django.db.models import Max


def _get_eur_rates(on_date=None):
    """
    Return dict {currency: Decimal(rate)} for the requested date.
    Falls back to the most recent available date if on_date has no data.
    EUR itself is always 1.0.
    """
    from .models import ExchangeRate  # avoid circular at module level

    qs = ExchangeRate.objects.filter(base_currency='EUR')
    if on_date:
        # Try exact date first, then fall back to latest <= on_date
        exact = qs.filter(date=on_date)
        if exact.exists():
            qs = exact
        else:
            latest = qs.filter(date__lte=on_date).aggregate(d=Max('date'))['d']
            if latest:
                qs = qs.filter(date=latest)

    if not qs.exists():
        # Absolute fallback: most recent date in DB
        latest = ExchangeRate.objects.aggregate(d=Max('date'))['d']
        if latest:
            qs = ExchangeRate.objects.filter(base_currency='EUR', date=latest)

    rates = {row.currency: Decimal(str(row.rate)) for row in qs}
    rates['EUR'] = Decimal('1.0')
    return rates


def get_rate(from_currency: str, to_currency: str, on_date=None) -> Decimal | None:
    """
    Return the exchange rate from_currency → to_currency.
    Returns None if rates are not available.
    """
    if from_currency == to_currency:
        return Decimal('1.0')

    rates = _get_eur_rates(on_date)
    if not rates or len(rates) < 2:
        return None

    from_rate = rates.get(from_currency)
    to_rate   = rates.get(to_currency)
    if from_rate is None or to_rate is None:
        return None

    # Both expressed as "units per EUR"
    # from_currency → EUR: 1 / from_rate
    # EUR → to_currency: * to_rate
    return (to_rate / from_rate).quantize(Decimal('0.000001'))


def convert(amount, from_currency: str, to_currency: str, on_date=None) -> Decimal | None:
    """
    Convert amount from from_currency to to_currency.
    Returns None if rates unavailable.
    """
    if from_currency == to_currency:
        return Decimal(str(amount))
    rate = get_rate(from_currency, to_currency, on_date)
    if rate is None:
        return None
    return (Decimal(str(amount)) * rate).quantize(Decimal('0.01'))


def latest_rates_date() -> date_type | None:
    """Return the most recent date for which we have ECB rates."""
    from .models import ExchangeRate
    return ExchangeRate.objects.aggregate(d=Max('date'))['d']


def all_pairs_for_date(on_date=None) -> dict:
    """
    Return a dict of all (from, to) → rate pairs for the given date.
    Useful for passing to templates as JSON.
    """
    currencies = ['EUR', 'USD', 'CHF']
    rates_eur = _get_eur_rates(on_date)
    pairs = {}
    for src in currencies:
        for dst in currencies:
            if src != dst:
                r = get_rate(src, dst, on_date)
                pairs[f'{src}_{dst}'] = float(r) if r else None
    return pairs
