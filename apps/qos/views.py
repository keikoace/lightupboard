import csv
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Sum, Count, F, Q
from .models import CDR, MinuteSummary
from apps.core.models import Company


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(val):
    return val.strip() if val and val.strip() else None


# ── Minutes Analysis ──────────────────────────────────────────────────────────

@login_required
def minutes_analysis(request):
    from django.db.models import Case, When, Value, CharField

    from_date  = _parse_date(request.GET.get('from'))
    to_date    = _parse_date(request.GET.get('to'))
    group_by   = request.GET.get('group', 'customer')
    customer_f = request.GET.get('customer', '')
    supplier_f = request.GET.get('supplier', '')
    has_run    = bool(from_date or to_date or customer_f or supplier_f)
    rows       = []

    # German mobile prefixes (49150-49159, 49160, 49162-49163, 49170-49179)
    MOBILE_PREFIXES = [
        '49150','49151','49152','49153','49154','49155','49156','49157','49158','49159',
        '49160','49162','49163',
        '49170','49171','49172','49173','49174','49175','49176','49177','49178','49179',
    ]
    mobile_whens = [When(dnis__startswith=p, then=Value('Mobile')) for p in MOBILE_PREFIXES]

    if has_run:
        qs = CDR.objects.annotate(
            dest_type=Case(
                *mobile_whens,
                default=Value('Fixed'),
                output_field=CharField(),
            )
        )
        if from_date:
            qs = qs.filter(start_time__date__gte=from_date)
        if to_date:
            qs = qs.filter(start_time__date__lte=to_date)
        if customer_f:
            qs = qs.filter(customer_id=customer_f)
        if supplier_f:
            qs = qs.filter(supplier_id=supplier_f)

        GROUP_MAP = {
            'type':        ('dest_type',),
            'destination': ('destination__name',),
            'customer':    ('customer__name',),
            'supplier':    ('supplier__name',),
            'day':         ('start_time__date',),
            'hour':        ('start_time__hour',),
        }
        val_fields = GROUP_MAP.get(group_by, ('customer__name',))

        agg = (
            qs.values(*val_fields)
            .annotate(
                call_count   = Count('id'),
                connected    = Count('id', filter=Q(answer_time__isnull=False)),
                total_seconds= Sum('duration_sec', filter=Q(answer_time__isnull=False)),  # answered only
                billed_secs  = Sum('sell_billed_duration_sec'),# 0 until process_cdrs runs
                total_revenue= Sum('sell_revenue'),
                total_cost   = Sum('buy_cost'),
            )
            .order_by('-total_seconds')[:200]
        )

        for r in agg:
            label_key = val_fields[0]
            label     = r.get(label_key) or '—'
            secs      = r['total_seconds'] or 0
            billed_s  = r['billed_secs'] or 0
            mins      = round(secs / 60, 2)
            billed_m  = round(billed_s / 60, 2)
            calls     = r['call_count'] or 0
            conn      = r['connected'] or 0
            asr       = round(conn / calls * 100, 1) if calls else 0
            acd       = round(secs / conn, 1) if conn else 0
            rev       = r['total_revenue'] or 0
            cost      = r['total_cost'] or 0
            rows.append({
                'label':         str(label),
                'calls':         calls,
                'connected':     conn,
                'minutes':       mins,
                'billed_minutes':billed_m,
                'asr':           asr,
                'acd':           acd,
                'revenue':       rev,
                'cost':          cost,
                'gp':            rev - cost,
            })

    customers = Company.objects.filter(role__in=['customer', 'both']).order_by('name')
    suppliers = Company.objects.filter(role__in=['supplier', 'both']).order_by('name')

    # Totals row
    totals = {
        'calls':          sum(r['calls'] for r in rows),
        'connected':      sum(r['connected'] for r in rows),
        'minutes':        round(sum(r['minutes'] for r in rows), 1),
        'billed_minutes': round(sum(r['billed_minutes'] for r in rows), 1),
        'revenue':        sum(r['revenue'] for r in rows),
        'cost':           sum(r['cost'] for r in rows),
        'gp':             sum(r['gp'] for r in rows),
    }

    return render(request, 'qos/minutes_analysis.html', {
        'rows':       rows,
        'totals':     totals,
        'has_run':    has_run,
        'group_by':   group_by,
        'customer_f': customer_f,
        'supplier_f': supplier_f,
        'customers':  customers,
        'suppliers':  suppliers,
    })


# ── Shared helper for customer/supplier minutes ───────────────────────────────

def _minutes_rows(qs, granularity, period_field, minutes_field, value_field):
    """
    Aggregate CDR queryset by (period, destination_name).
    Returns list of dicts ready for template rendering.
    granularity: 'daily' | 'hourly'
    period_field: annotated name for the truncated datetime
    minutes_field: 'sell_billed_duration_sec' or 'buy_billed_duration_sec'
    value_field: 'sell_revenue' or 'buy_cost'
    """
    from django.db.models.functions import TruncDay, TruncHour
    trunc_fn = TruncDay if granularity == 'daily' else TruncHour
    agg = (
        qs
        .annotate(period=trunc_fn('start_time'))
        .values('period', 'destination__name')
        .annotate(
            total_calls=Count('id'),
            connected_calls=Count('id', filter=Q(answer_time__isnull=False)),
            _secs=Sum(minutes_field),
            value=Sum(value_field),
        )
        .order_by('-period', 'destination__name')[:500]
    )
    rows = []
    tot_calls = tot_conn = tot_secs = 0
    tot_value = 0
    for r in agg:
        calls = r['total_calls'] or 0
        conn  = r['connected_calls'] or 0
        secs  = r['_secs'] or 0
        val   = r['value'] or 0
        tot_calls += calls
        tot_conn  += conn
        tot_secs  += secs
        tot_value += val
        rows.append({
            'period':      r['period'],
            'destination': r['destination__name'] or '—',
            'total_calls': calls,
            'connected':   conn,
            'minutes':     round(secs / 60, 2),
            'asr':         round(conn / calls * 100, 1) if calls else 0,
            'value':       val,
        })
    totals = {
        'total_calls': tot_calls,
        'connected':   tot_conn,
        'minutes':     round(tot_secs / 60, 2),
        'asr':         round(tot_conn / tot_calls * 100, 1) if tot_calls else 0,
        'value':       round(tot_value, 4),
    }
    return rows, totals


# ── Customer Minutes ──────────────────────────────────────────────────────────

@login_required
def customer_minutes(request):
    companies    = Company.objects.filter(role__in=['customer', 'both']).order_by('name')
    selected     = request.GET.get('company')
    granularity  = request.GET.get('granularity', 'daily')
    from_date    = request.GET.get('from', '')
    to_date      = request.GET.get('to', '')
    rows, totals = [], {}
    if selected:
        qs = CDR.objects.filter(customer_id=selected)
        if from_date:
            qs = qs.filter(start_time__date__gte=from_date)
        if to_date:
            qs = qs.filter(start_time__date__lte=to_date)
        rows, totals = _minutes_rows(qs, granularity, 'period', 'sell_billed_duration_sec', 'sell_revenue')
    return render(request, 'qos/customer_minutes.html', {
        'companies':   companies,
        'selected':    selected,
        'granularity': granularity,
        'from_date':   from_date,
        'to_date':     to_date,
        'rows':        rows,
        'totals':      totals,
        'value_label': 'Revenue',
    })


# ── Supplier Minutes ──────────────────────────────────────────────────────────

@login_required
def supplier_minutes(request):
    companies    = Company.objects.filter(role__in=['supplier', 'both']).order_by('name')
    selected     = request.GET.get('company')
    granularity  = request.GET.get('granularity', 'daily')
    from_date    = request.GET.get('from', '')
    to_date      = request.GET.get('to', '')
    rows, totals = [], {}
    if selected:
        qs = CDR.objects.filter(supplier_id=selected)
        if from_date:
            qs = qs.filter(start_time__date__gte=from_date)
        if to_date:
            qs = qs.filter(start_time__date__lte=to_date)
        rows, totals = _minutes_rows(qs, granularity, 'period', 'buy_billed_duration_sec', 'buy_cost')
    return render(request, 'qos/supplier_minutes.html', {
        'companies':   companies,
        'selected':    selected,
        'granularity': granularity,
        'from_date':   from_date,
        'to_date':     to_date,
        'rows':        rows,
        'totals':      totals,
        'value_label': 'Cost',
    })



# ── DDI Minutes ───────────────────────────────────────────────────────────────

@login_required
def ddi_minutes(request):
    from apps.ddi.models import DDINumber

    from_date = _parse_date(request.GET.get('from'))
    to_date   = _parse_date(request.GET.get('to'))
    group_by  = request.GET.get('group', 'number')
    has_run   = bool(from_date or to_date)
    rows      = []

    if has_run:
        qs = CDR.objects.filter(dnis__in=DDINumber.objects.values('number'))

        if from_date:
            qs = qs.filter(start_time__date__gte=from_date)
        if to_date:
            qs = qs.filter(start_time__date__lte=to_date)

        group_field = 'customer__name' if group_by == 'customer' else 'dnis'
        agg = (
            qs.values(group_field)
            .annotate(
                label=F(group_field),
                call_count=Count('id'),
                connected=Count('id', filter=Q(duration_sec__gt=0)),
                total_seconds=Sum('sell_billed_duration_sec'),
                total_revenue=Sum('sell_revenue'),
                total_cost=Sum('buy_cost'),
            )
            .order_by('-total_seconds')[:200]
        )

        for r in agg:
            label = r.get('label') or '—'
            secs  = r['total_seconds'] or 0
            calls = r['call_count'] or 0
            conn  = r['connected'] or 0
            asr   = round(conn / calls * 100, 1) if calls else 0
            rev   = r['total_revenue'] or 0
            cost  = r['total_cost'] or 0
            rows.append({
                'label':   str(label),
                'calls':   calls,
                'minutes': round(secs / 60, 1),
                'asr':     asr,
                'revenue': rev,
                'cost':    cost,
                'gp':      rev - cost,
            })

    return render(request, 'qos/ddi_minutes.html', {
        'rows': rows,
        'has_run': has_run,
    })


# ── CDR Extract ───────────────────────────────────────────────────────────────

@login_required
def cdr_extract(request):
    from apps.core.models import Destination
    customers    = Company.objects.filter(role__in=['customer', 'both']).order_by('name')
    suppliers    = Company.objects.filter(role__in=['supplier', 'both']).order_by('name')
    destinations = Destination.objects.filter(is_active=True).order_by('name')

    qs = CDR.objects.select_related('customer', 'supplier', 'destination').order_by('-start_time')

    from_val      = request.GET.get('from')
    to_val        = request.GET.get('to')
    customer_id   = request.GET.get('customer')
    supplier_id   = request.GET.get('supplier')
    dnis          = request.GET.get('dnis', '').strip()
    destination_id = request.GET.get('destination')
    cause         = request.GET.get('cause', '').strip()

    if from_val:
        qs = qs.filter(start_time__gte=from_val)
    if to_val:
        qs = qs.filter(start_time__lte=to_val)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if supplier_id:
        qs = qs.filter(supplier_id=supplier_id)
    if dnis:
        qs = qs.filter(dnis__startswith=dnis)
    if destination_id:
        qs = qs.filter(destination_id=destination_id)
    if cause:
        qs = qs.filter(disconnect_cause=cause)

    cdrs = qs[:500]

    if 'export' in request.GET:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="cdr_extract.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Start Time', 'Customer', 'Supplier', 'ANI', 'DNIS', 'Destination',
            'Duration (s)', 'Sell Billed (s)', 'Buy Billed (s)',
            'Sell Rate', 'Buy Rate', 'Revenue', 'Cost', 'Gross Profit', 'Cause',
        ])
        for c in cdrs:
            writer.writerow([
                c.start_time,
                c.customer.name if c.customer_id else '',
                c.supplier.name if c.supplier_id else '',
                c.ani, c.dnis,
                c.destination.name if c.destination_id else '',
                c.duration_sec,
                c.sell_billed_duration_sec,
                c.buy_billed_duration_sec,
                c.sell_rate, c.buy_rate,
                c.sell_revenue, c.buy_cost, c.gross_profit,
                c.disconnect_cause,
            ])
        return response

    return render(request, 'qos/cdr_extract.html', {
        'cdrs':           cdrs,
        'customers':      customers,
        'suppliers':      suppliers,
        'destinations':   destinations,
        'destination_id': destination_id or '',
        'cause':          cause,
    })


# ── DDI CDR Extract ───────────────────────────────────────────────────────────

@login_required
def ddi_cdr_extract(request):
    from apps.ddi.models import DDINumber

    qs = CDR.objects.filter(dnis__in=DDINumber.objects.values('number')).select_related(
        'customer', 'supplier', 'destination'
    ).order_by('-start_time')

    from_val = request.GET.get('from')
    to_val   = request.GET.get('to')
    number_q = request.GET.get('number', '').strip()

    if from_val:
        qs = qs.filter(start_time__gte=from_val)
    if to_val:
        qs = qs.filter(start_time__lte=to_val)
    if number_q:
        qs = qs.filter(dnis__startswith=number_q)

    cdrs = qs[:500]

    if 'export' in request.GET:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="ddi_cdr_extract.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Start Time', 'DDI Number', 'Customer', 'ANI',
            'Duration (s)', 'Sell Billed (s)', 'Buy Billed (s)',
            'Revenue', 'Cost', 'Cause',
        ])
        for c in cdrs:
            writer.writerow([
                c.start_time, c.dnis,
                c.customer.name if c.customer_id else '',
                c.ani, c.duration_sec,
                c.sell_billed_duration_sec,
                c.buy_billed_duration_sec,
                c.sell_revenue, c.buy_cost, c.disconnect_cause,
            ])
        return response

    return render(request, 'qos/ddi_cdr_extract.html', {'cdrs': cdrs})
