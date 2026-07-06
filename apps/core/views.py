import json
from datetime import timedelta, date
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.core.models import Switch, Destination
from apps.alerts.models import AlertEvent
from apps.qos.models import MinuteSummary


def _get_switches(request):
    return Switch.objects.filter(is_active=True)


@login_required
def dashboard(request):
    from django.db.models import Sum, Count, Q
    from decimal import Decimal
    switches = _get_switches(request)
    today = date.today()

    # ── Today's KPIs from CDR ─────────────────────────────────────────────────
    from apps.qos.models import CDR
    today_agg = CDR.objects.filter(
        start_time__date=today, is_processed=True
    ).aggregate(
        total_sec=Sum('sell_billed_duration_sec'),
        revenue=Sum('sell_revenue'),
        cost=Sum('buy_cost'),
        calls=Count('id'),
        connected=Count('id', filter=Q(duration_sec__gt=0)),
    )
    total_mins    = round(float(today_agg['total_sec'] or 0) / 60, 1)
    gross_profit  = round(float((today_agg['revenue'] or 0) - (today_agg['cost'] or 0)), 2)
    calls         = today_agg['calls'] or 0
    connected     = today_agg['connected'] or 0
    asr           = round(connected / calls * 100, 1) if calls else 0
    open_alerts   = AlertEvent.objects.filter(status=AlertEvent.STATUS_OPEN).count()

    kpi = {
        'total_minutes': total_mins,
        'gross_profit':  gross_profit,
        'asr':           asr,
        'open_alerts':   open_alerts,
    }

    # ── Weekly totals (last 4 Mon–Sun weeks) ──────────────────────────────────
    weekly_totals = []
    for i in range(3, -1, -1):
        week_start = today - timedelta(days=today.weekday() + 7 * i)
        week_end   = week_start + timedelta(days=6)
        agg = (
            MinuteSummary.objects
            .filter(hour__date__gte=week_start, hour__date__lte=week_end, side='customer')
            .aggregate(t=Sum('total_minutes'))
        )
        weekly_totals.append({
            'label':   str(week_start),
            'minutes': float(agg['t'] or 0),
        })

    # ── Hourly chart: real MinuteSummary data per week ────────────────────────
    hours = [f'{h}:00' for h in range(24)]
    datasets = []
    colors = ['rgba(13,110,253,0.8)', 'rgba(13,110,253,0.55)',
              'rgba(13,110,253,0.35)', 'rgba(13,110,253,0.2)']
    for idx, wk in enumerate(weekly_totals):
        week_start = date.fromisoformat(wk['label'])
        week_end   = week_start + timedelta(days=6)
        # Aggregate minutes per hour-of-day across the week
        buckets = (
            MinuteSummary.objects
            .filter(hour__date__gte=week_start, hour__date__lte=week_end, side='customer')
            .values('hour__hour')
            .annotate(t=Sum('total_minutes'))
        )
        data = [0.0] * 24
        for b in buckets:
            h = b['hour__hour']
            if 0 <= h < 24:
                data[h] = round(float(b['t'] or 0), 1)
        datasets.append({
            'label': wk['label'],
            'data': data,
            'borderColor': colors[idx],
            'backgroundColor': colors[idx],
        })
    hourly_chart_data = json.dumps({'labels': hours, 'datasets': datasets})

    return render(request, 'dashboard.html', {
        'switches':          switches,
        'weekly_totals':     weekly_totals,
        'hourly_chart_data': hourly_chart_data,
        'kpi':               kpi,
    })


# ── Temporary Destination Import (remove after use) ───────────────────────────

@login_required
@csrf_exempt
@require_POST
def import_destinations(request):
    try:
        data = json.loads(request.body)
        created = updated = 0
        for item in data:
            obj, c = Destination.objects.update_or_create(
                prefix=item['prefix'],
                defaults={
                    'name': item['name'],
                    'country': item['country'],
                    'is_active': item['is_active'],
                }
            )
            if c:
                created += 1
            else:
                updated += 1
        return JsonResponse({'status': 'ok', 'created': created, 'updated': updated})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
