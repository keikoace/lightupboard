"""
Finance context processors.
Automatically injects currency rates into every Finance page so the
floating FX widget works without each view needing to pass data.
"""
import json


def fx_rates(request):
    """
    Inject today's FX pair rates as JSON into Finance app contexts.
    Only runs the DB query when the current URL belongs to the finance app.
    """
    resolver_match = getattr(request, 'resolver_match', None)
    if resolver_match and getattr(resolver_match, 'app_name', '') == 'finance':
        try:
            from .currency import all_pairs_for_date
            pairs = all_pairs_for_date()
            return {'fx_pairs_json': json.dumps(pairs)}
        except Exception:
            pass
    return {}
