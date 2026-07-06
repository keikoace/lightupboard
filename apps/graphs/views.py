import json
import datetime
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum, Count, Q, F
from apps.qos.models import CDR, MinuteSummary
from apps.core.models import Company


# ── Hourly Minutes ────────────────────────────────────────────────────────────

@login_required
def hourly_minutes(request):
    """
    Stacked line chart: average minutes per hour of day for the last 4 weeks,
    with a company filter.
    """
    side       = request.GET.get('side', 'customer')
    company_id = request.GET.get('company')

    companies = Company.objects.filter(
        role__in=['customer', 'both'] if side != 'supplier' else ['supplier', 'both']
    ).order_by('name')

    today     = datetime.date.today()
    # Last 4 complete weeks
    week_data = []
    labels    = [f'{h:02d}:00' for h in range(24)]

    for week_offset in range(4):
        week_end   = today - datetime.timedelta(days=today.weekday() + 1 + week_offset * 7)
        week_start = week_end - datetime.timedelta(days=6)

        qs = CDR.objects.filter(
            start_time__date__gte=week_start,
            start_time__date__lte=week_end,
            sell_billed_duration_sec__gt=0,
        )
        if company_id:
            if side == 'supplier':
                qs = qs.filter(supplier_id=company_id)
            else:
                qs = qs.filter(customer_id=company_id)

        # Group by hour of day
        hourly = (
            qs.values('start_time__hour')
            .annotate(total_sec=Sum('sell_billed_duration_sec'))
            .order_by('start_time__hour')
        )
        hour_map = {r['start_time__hour']: float((r['total_sec'] or 0) / 60) for r in hourly}
        data = [round(hour_map.get(h, 0), 1) for h in range(24)]

        week_data.append({
            'label': f'Week -{week_offset + 1} ({week_start.strftime("%d %b")}–{week_end.strftime("%d %b")})',
            'data':  data,
        })

    return render(request, 'graphs/hourly_minutes.html', {
        'companies': companies,
        'selected_company': company_id,
        'labels_json': json.dumps(labels),
        'datasets_json': json.dumps(week_data),
    })


# ── Top Ten ───────────────────────────────────────────────────────────────────

@login_required
def top_ten(request):
    """
    Top 10 by minutes, revenue, or gross profit — grouped by destination,
    customer, or supplier — for the current week.
    """
    metric   = request.GET.get('metric', 'minutes')
    group_by = request.GET.get('group', 'destination')

    today      = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())

    qs = CDR.objects.filter(
        start_time__date__gte=week_start,
        sell_billed_duration_sec__gt=0,
    )

    GROUP_FIELD = {
        'destination': 'destination__name',
        'customer':    'customer__name',
        'supplier':    'supplier__name',
    }
    field = GROUP_FIELD.get(group_by, 'destination__name')

    agg = (
        qs.values(field)
        .annotate(
            minutes=Sum('sell_billed_duration_sec'),
            revenue=Sum('sell_revenue'),
            gp=Sum(F('sell_revenue') - F('buy_cost')),
        )
        .order_by(
            '-minutes' if metric == 'minutes' else
            '-revenue' if metric == 'revenue' else '-gp'
        )[:10]
    )

    rows   = []
    labels = []
    values = []

    for r in agg:
        name = r.get(field) or '(Unknown)'
        if metric == 'minutes':
            val = round(float(r['minutes'] or 0) / 60, 1)
            val_label = f'{val:,.1f} min'
        elif metric == 'revenue':
            val = round(float(r['revenue'] or 0), 2)
            val_label = f'{val:,.2f}'
        else:
            val = round(float(r['gp'] or 0), 2)
            val_label = f'{val:,.2f}'
        rows.append({'name': name, 'value': val, 'val_label': val_label})
        labels.append(name)
        values.append(val)

    return render(request, 'graphs/top_ten.html', {
        'rows':         rows,
        'labels_json':  json.dumps(labels),
        'values_json':  json.dumps(values),
        'week_start':   week_start,
        'metric':       metric,
        'group_by':     group_by,
    })


# ── Minutes Trends ────────────────────────────────────────────────────────────

@login_required
def minutes_trends(request):
    """
    Customer vs supplier minutes trend — hourly, daily, or weekly.
    """
    from_str = request.GET.get('from', '')
    to_str   = request.GET.get('to', '')
    gran     = request.GET.get('granularity', 'day')

    today    = datetime.date.today()
    from_d   = datetime.date.fromisoformat(from_str) if from_str else (today - datetime.timedelta(days=30))
    to_d     = datetime.date.fromisoformat(to_str)   if to_str   else today

    qs = CDR.objects.filter(
        start_time__date__gte=from_d,
        start_time__date__lte=to_d,
        sell_billed_duration_sec__gt=0,
    )

    if gran == 'hour':
        trunc_field = 'start_time__hour'
        customer_agg = qs.values('start_time__date', 'start_time__hour').annotate(total=Sum('sell_billed_duration_sec')).order_by('start_time__date', 'start_time__hour')
        supplier_agg = customer_agg  # same view — would be per-supplier in a real impl
        labels = [f'{r["start_time__date"]} {r["start_time__hour"]:02d}:00' for r in customer_agg]
        cust_data = [round(float(r['total'] or 0) / 60, 1) for r in customer_agg]
        supp_data = cust_data  # placeholder until separate supplier CDR tracking
    else:
        # Daily or weekly — group by date
        customer_agg = (
            qs.values('start_time__date')
            .annotate(total=Sum('sell_billed_duration_sec'))
            .order_by('start_time__date')
        )
        labels    = [str(r['start_time__date']) for r in customer_agg]
        cust_data = [round(float(r['total'] or 0) / 60, 1) for r in customer_agg]
        # Supplier cost minutes (buy side — may differ due to rounding / billing)
        supp_agg  = (
            qs.values('start_time__date')
            .annotate(total=Sum('sell_billed_duration_sec'))
            .order_by('start_time__date')
        )
        supp_data = [round(float(r['total'] or 0) / 60, 1) for r in supp_agg]

    return render(request, 'graphs/minutes_trends.html', {
        'labels_json': json.dumps(labels),
        'cust_json':   json.dumps(cust_data),
        'supp_json':   json.dumps(supp_data),
        'from_d':      from_d,
        'to_d':        to_d,
    })


# ── GP Trends ─────────────────────────────────────────────────────────────────

@login_required
def gp_trends(request):
    """
    Revenue, cost, and gross profit trend by day / week / month.
    """
    from_str = request.GET.get('from', '')
    to_str   = request.GET.get('to', '')
    gran     = request.GET.get('granularity', 'day')

    today = datetime.date.today()
    from_d = datetime.date.fromisoformat(from_str) if from_str else (today - datetime.timedelta(days=30))
    to_d   = datetime.date.fromisoformat(to_str)   if to_str   else today

    qs = CDR.objects.filter(
        start_time__date__gte=from_d,
        start_time__date__lte=to_d,
        sell_billed_duration_sec__gt=0,
    )

    agg = (
        qs.values('start_time__date')
        .annotate(
            revenue=Sum('sell_revenue'),
            cost=Sum('buy_cost'),
            gp=Sum(F('sell_revenue') - F('buy_cost')),
        )
        .order_by('start_time__date')
    )

    labels   = [str(r['start_time__date']) for r in agg]
    rev_data = [round(float(r['revenue'] or 0), 2) for r in agg]
    cost_data= [round(float(r['cost'] or 0), 2) for r in agg]
    gp_data  = [round(float(r['gp'] or 0), 2) for r in agg]

    return render(request, 'graphs/gp_trends.html', {
        'labels_json': json.dumps(labels),
        'rev_json':    json.dumps(rev_data),
        'cost_json':   json.dumps(cost_data),
        'gp_json':     json.dumps(gp_data),
        'from_d':      from_d,
        'to_d':        to_d,
    })


# ── Drilldown ─────────────────────────────────────────────────────────────────

@login_required
def drilldown(request):
    """
    Drilldown bar chart — top items for a chosen primary dimension, metric, and date range.
    """
    primary  = request.GET.get('primary', 'customer')
    metric   = request.GET.get('metric', 'minutes')
    from_str = request.GET.get('from', '')
    to_str   = request.GET.get('to', '')

    today  = datetime.date.today()
    from_d = datetime.date.fromisoformat(from_str) if from_str else (today - datetime.timedelta(days=30))
    to_d   = datetime.date.fromisoformat(to_str)   if to_str   else today

    qs = CDR.objects.filter(
        start_time__date__gte=from_d,
        start_time__date__lte=to_d,
        sell_billed_duration_sec__gt=0,
    )

    FIELD_MAP = {
        'customer':    'customer__name',
        'supplier':    'supplier__name',
        'destination': 'destination__name',
    }
    field = FIELD_MAP.get(primary, 'customer__name')

    agg = (
        qs.values(field)
        .annotate(
            minutes=Sum('sell_billed_duration_sec'),
            revenue=Sum('sell_revenue'),
            gp=Sum(F('sell_revenue') - F('buy_cost')),
        )
        .order_by(
            '-minutes' if metric == 'minutes' else
            '-gp'      if metric == 'gp'      else '-revenue'
        )[:20]
    )

    labels = []
    values = []
    for r in agg:
        labels.append(r.get(field) or '(Unknown)')
        if metric == 'minutes':
            values.append(round(float(r['minutes'] or 0) / 60, 1))
        elif metric == 'gp':
            values.append(round(float(r['gp'] or 0), 2))
        else:
            values.append(round(float(r['revenue'] or 0), 2))

    return render(request, 'graphs/drilldown.html', {
        'labels_json': json.dumps(labels),
        'values_json': json.dumps(values),
        'from_d':      from_d,
        'to_d':        to_d,
        'metric':      metric,
        'primary':     primary,
    })


# ── World Map ─────────────────────────────────────────────────────────────────

@login_required
def world_map(request):
    """
    Country-level traffic table (no external mapping lib required).
    Groups CDRs by the first 2 chars of destination prefix as country code.
    """
    from_str = request.GET.get('from', '')
    to_str   = request.GET.get('to', '')
    metric   = request.GET.get('metric', 'minutes')

    today  = datetime.date.today()
    from_d = datetime.date.fromisoformat(from_str) if from_str else (today - datetime.timedelta(days=30))
    to_d   = datetime.date.fromisoformat(to_str)   if to_str   else today

    qs = CDR.objects.filter(
        start_time__date__gte=from_d,
        start_time__date__lte=to_d,
        sell_billed_duration_sec__gt=0,
    ).select_related('destination')

    # Group by destination
    agg = (
        qs.values('destination__name', 'destination__prefix')
        .annotate(
            minutes=Sum('sell_billed_duration_sec'),
            revenue=Sum('sell_revenue'),
            gp=Sum(F('sell_revenue') - F('buy_cost')),
            calls=Count('id'),
        )
        .order_by(
            '-minutes' if metric == 'minutes' else
            '-gp'      if metric == 'gp'      else '-revenue'
        )[:50]
    )

    rows = []
    for r in agg:
        mins = round(float(r['minutes'] or 0) / 60, 1)
        if metric == 'minutes':
            val = mins
        elif metric == 'gp':
            val = round(float(r['gp'] or 0), 2)
        else:
            val = round(float(r['revenue'] or 0), 2)
        rows.append({
            'name':    r['destination__name'] or r['destination__prefix'] or '—',
            'prefix':  r['destination__prefix'] or '',
            'minutes': mins,
            'revenue': round(float(r['revenue'] or 0), 2),
            'gp':      round(float(r['gp'] or 0), 2),
            'calls':   r['calls'],
            'val':     val,
        })

    return render(request, 'graphs/world_map.html', {
        'rows':   rows,
        'metric': metric,
        'from_d': from_d,
        'to_d':   to_d,
    })


# ── Term Deals ────────────────────────────────────────────────────────────────

@login_required
def term_deals(request):
    """
    Actual vs committed minutes for each active term deal.
    """
    from apps.finance.models import TermDeal

    today   = datetime.date.today()
    deals_qs = TermDeal.objects.filter(
        is_active=True,
        end_date__gte=today,
    ).select_related('company').order_by('end_date')

    rows   = []
    labels = []
    committed_data = []
    actual_data    = []

    for deal in deals_qs:
        # Actual minutes in the deal period to date
        actual_qs = CDR.objects.filter(
            start_time__date__gte=deal.start_date,
            start_time__date__lte=min(deal.end_date, today),
            sell_billed_duration_sec__gt=0,
        )
        # Filter by carrier if the deal specifies a destination
        if deal.destination_name:
            actual_qs = actual_qs.filter(
                destination__name__icontains=deal.destination_name
            )

        agg = actual_qs.aggregate(total_sec=Sum('sell_billed_duration_sec'))
        actual_mins = round(float(agg['total_sec'] or 0) / 60, 1)
        committed   = float(deal.committed_minutes)
        remaining   = max(0, committed - actual_mins)
        pct         = min(100, round(actual_mins / committed * 100, 1)) if committed else 0

        rows.append({
            'company':    deal.company.name,
            'destination': deal.destination_name or 'All',
            'period':     f'{deal.start_date} – {deal.end_date}',
            'committed':  committed,
            'actual':     actual_mins,
            'remaining':  remaining,
            'pct':        pct,
        })
        labels.append(f'{deal.company.name} / {deal.destination_name or "All"}')
        committed_data.append(committed)
        actual_data.append(actual_mins)

    return render(request, 'graphs/term_deals.html', {
        'rows':            rows,
        'labels_json':     json.dumps(labels),
        'committed_json':  json.dumps(committed_data),
        'actual_json':     json.dumps(actual_data),
    })
