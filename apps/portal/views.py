"""
Customer portal views — completely isolated from the internal staff system.
Access is granted by linking a Django User to a Company via Company.portal_users.
"""
import datetime
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404

import csv
from django.http import StreamingHttpResponse

from apps.core.models import Company
from apps.finance.models import Invoice, InvoiceLine
from apps.ddi.models import DDINumber


# ── Access control ────────────────────────────────────────────────────────────

def portal_login_required(view_fn):
    """
    Decorator: user must be authenticated AND have at least one linked company.
    Staff/superusers are NOT automatically granted portal access — they must be
    explicitly added to a company's portal_users to prevent accidental exposure.
    """
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('portal:login')
        company = _get_portal_company(request.user)
        if company is None:
            messages.error(request, 'Your account is not linked to any company. Please contact support.')
            logout(request)
            return redirect('portal:login')
        return view_fn(request, *args, **kwargs)
    return wrapper


def _get_portal_company(user):
    """Return the first Company linked to this portal user, or None."""
    return (
        Company.objects
        .filter(portal_users=user, is_active=True)
        .first()
    )


# ── Auth ──────────────────────────────────────────────────────────────────────

def portal_root(request):
    if request.user.is_authenticated and _get_portal_company(request.user):
        return redirect('portal:dashboard')
    return redirect('portal:login')


def portal_login(request):
    if request.user.is_authenticated and _get_portal_company(request.user):
        return redirect('portal:dashboard')

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        company = _get_portal_company(user)
        if company is None:
            messages.error(request, 'Your account does not have portal access.')
        else:
            login(request, user)
            return redirect(request.GET.get('next', 'portal:dashboard'))

    return render(request, 'portal/login.html', {'form': form})


def portal_logout(request):
    logout(request)
    return redirect('portal:login')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@portal_login_required
def dashboard(request):
    company = _get_portal_company(request.user)
    today   = datetime.date.today()

    # Recent invoices (last 5)
    recent_invoices = (
        Invoice.objects
        .filter(company=company, invoice_type=Invoice.TYPE_SALES)
        .order_by('-issue_date')[:5]
    )

    # Outstanding balance
    outstanding = (
        Invoice.objects
        .filter(company=company, invoice_type=Invoice.TYPE_SALES,
                status__in=[Invoice.STATUS_SENT, Invoice.STATUS_OVERDUE])
        .aggregate(bal=Sum('total_amount'), paid=Sum('amount_paid'))
    )
    balance_due = (outstanding['bal'] or 0) - (outstanding['paid'] or 0)

    # Overdue count
    overdue_count = Invoice.objects.filter(
        company=company, status=Invoice.STATUS_OVERDUE
    ).count()

    # Traffic this month
    from apps.qos.models import CDR
    month_start = today.replace(day=1)
    traffic = CDR.objects.filter(
        customer=company,
        start_time__date__gte=month_start,
        sell_billed_duration_sec__gt=0,
    ).aggregate(
        minutes=Sum('sell_billed_duration_sec'),
        calls=Count('id'),
    )
    minutes_this_month = round((traffic['minutes'] or 0) / 60, 0)

    # DID count
    did_count = DDINumber.objects.filter(customer=company).count()

    return render(request, 'portal/dashboard.html', {
        'company':            company,
        'recent_invoices':    recent_invoices,
        'balance_due':        balance_due,
        'overdue_count':      overdue_count,
        'minutes_this_month': minutes_this_month,
        'calls_this_month':   traffic['calls'] or 0,
        'did_count':          did_count,
        'today':              today,
    })


# ── Invoices ──────────────────────────────────────────────────────────────────

@portal_login_required
def invoices(request):
    company = _get_portal_company(request.user)
    qs = (
        Invoice.objects
        .filter(company=company, invoice_type=Invoice.TYPE_SALES)
        .order_by('-issue_date')
    )
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    return render(request, 'portal/invoices.html', {
        'company':       company,
        'invoices':      qs,
        'status_filter': status_filter,
        'status_choices': Invoice.STATUS_CHOICES,
    })


@portal_login_required
def invoice_detail(request, pk):
    company = _get_portal_company(request.user)
    invoice = get_object_or_404(
        Invoice, pk=pk, company=company, invoice_type=Invoice.TYPE_SALES
    )
    lines = invoice.lines.order_by('sort_order')
    return render(request, 'portal/invoice_detail.html', {
        'company': company,
        'invoice': invoice,
        'lines':   lines,
    })


@portal_login_required
def invoice_print(request, pk):
    """Reuses the internal print template — no base layout, just the document."""
    company = _get_portal_company(request.user)
    invoice = get_object_or_404(
        Invoice, pk=pk, company=company, invoice_type=Invoice.TYPE_SALES
    )
    lines = invoice.lines.order_by('sort_order')
    # Reuse the existing internal print template
    return render(request, 'finance/invoice_print.html', {
        'invoice': invoice,
        'lines':   lines,
    })


# ── Traffic ───────────────────────────────────────────────────────────────────

@portal_login_required
def traffic(request):
    from apps.qos.models import CDR

    company = _get_portal_company(request.user)
    today   = datetime.date.today()

    year  = int(request.GET.get('year',  today.year))
    month = int(request.GET.get('month', today.month))

    period_start = datetime.date(year, month, 1)
    period_end   = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)

    rows = (
        CDR.objects
        .filter(
            customer=company,
            start_time__date__gte=period_start,
            start_time__date__lt=period_end,
            sell_billed_duration_sec__gt=0,
        )
        .values('destination__name', 'destination__prefix')
        .annotate(
            total_minutes=Sum('sell_billed_duration_sec'),
            call_count=Count('id'),
            total_revenue=Sum('sell_revenue'),
        )
        .order_by('-total_minutes')
    )

    # Convert seconds → minutes
    rows = [
        {
            'dest_name':   r['destination__name']   or '(Unknown)',
            'dest_prefix': r['destination__prefix'] or '',
            'minutes':     round(r['total_minutes'] / 60, 1),
            'call_count':  r['call_count'],
            'revenue':     r['total_revenue'],
        }
        for r in rows
    ]

    totals = {
        'minutes':   sum(r['minutes'] for r in rows),
        'calls':     sum(r['call_count'] for r in rows),
        'revenue':   sum((r['revenue'] or 0) for r in rows),
    }

    years  = list(range(today.year - 2, today.year + 1))
    months = [(i, datetime.date(2000, i, 1).strftime('%B')) for i in range(1, 13)]

    return render(request, 'portal/traffic.html', {
        'company':      company,
        'rows':         rows,
        'totals':       totals,
        'year':         year,
        'month':        month,
        'years':        years,
        'months':       months,
        'period_start': period_start,
        'currency':     company.currency,
    })


# ── DIDs ──────────────────────────────────────────────────────────────────────

@portal_login_required
def dids(request):
    company = _get_portal_company(request.user)
    did_list = (
        DDINumber.objects
        .filter(customer=company)
        .select_related('destination')
        .order_by('number')
    )
    return render(request, 'portal/dids.html', {
        'company':  company,
        'did_list': did_list,
    })


# ── Rates ─────────────────────────────────────────────────────────────────────

@portal_login_required
def rates(request):
    """Show the client's sell-side rate table. Buy rates are never exposed."""
    from apps.rates.models import Tariff, Rate

    company = _get_portal_company(request.user)

    # Active sell tariffs assigned to this company
    tariffs = (
        Tariff.objects
        .filter(company=company, side=Tariff.SIDE_SELL, is_active=True)
        .prefetch_related('rates__destination')
        .order_by('name')
    )

    selected_id = request.GET.get('tariff')
    selected_tariff = None
    rate_rows = []

    if tariffs:
        # Default to first tariff if none selected
        try:
            selected_tariff = tariffs.get(pk=selected_id) if selected_id else tariffs.first()
        except Tariff.DoesNotExist:
            selected_tariff = tariffs.first()

    if selected_tariff:
        q = request.GET.get('q', '').strip()
        rate_qs = (
            selected_tariff.rates
            .select_related('destination', 'origin_group')
            .order_by('destination__name', 'prefix')
        )
        if q:
            rate_qs = rate_qs.filter(
                destination__name__icontains=q
            ) | rate_qs.filter(prefix__startswith=q)
        rate_rows = rate_qs

    return render(request, 'portal/rates.html', {
        'company':          company,
        'tariffs':          tariffs,
        'selected_tariff':  selected_tariff,
        'rate_rows':        rate_rows,
        'q':                request.GET.get('q', ''),
    })


# ── CDR Export ────────────────────────────────────────────────────────────────

@portal_login_required
def cdr_export(request):
    """Stream a CSV of the company's CDRs for the requested month. Sell-side only."""
    from apps.qos.models import CDR

    company = _get_portal_company(request.user)
    today   = datetime.date.today()

    year  = int(request.GET.get('year',  today.year))
    month = int(request.GET.get('month', today.month))

    period_start = datetime.date(year, month, 1)
    period_end   = (
        datetime.date(year + 1, 1, 1) if month == 12
        else datetime.date(year, month + 1, 1)
    )

    qs = (
        CDR.objects
        .filter(
            customer=company,
            start_time__date__gte=period_start,
            start_time__date__lt=period_end,
        )
        .select_related('destination')
        .order_by('start_time')
        # Only sell-side fields — buy_rate / buy_cost intentionally excluded
        .values(
            'call_id', 'start_time', 'answer_time', 'end_time',
            'ani', 'dnis',
            'destination__name', 'destination__prefix',
            'sell_billed_duration_sec', 'sell_rate', 'sell_revenue',
            'disconnect_cause',
        )
    )

    filename = f'cdrs_{company.name.replace(" ", "_")}_{year}-{month:02d}.csv'

    def rows():
        header = [
            'Call ID', 'Start Time', 'Answer Time', 'End Time',
            'ANI', 'DNIS',
            'Destination', 'Prefix',
            'Billed Seconds', 'Rate (per min)', 'Charge',
            'Disconnect Cause',
        ]
        yield header
        for r in qs.iterator(chunk_size=500):
            yield [
                r['call_id'],
                r['start_time'].strftime('%Y-%m-%d %H:%M:%S') if r['start_time'] else '',
                r['answer_time'].strftime('%Y-%m-%d %H:%M:%S') if r['answer_time'] else '',
                r['end_time'].strftime('%Y-%m-%d %H:%M:%S') if r['end_time'] else '',
                r['ani'], r['dnis'],
                r['destination__name'] or '',
                r['destination__prefix'] or '',
                r['sell_billed_duration_sec'],
                r['sell_rate'],
                r['sell_revenue'],
                r['disconnect_cause'] or '',
            ]

    class EchoWriter:
        def write(self, value): return value

    pseudo_buffer = EchoWriter()
    writer = csv.writer(pseudo_buffer)

    response = StreamingHttpResponse(
        (writer.writerow(row) for row in rows()),
        content_type='text/csv',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── Account ───────────────────────────────────────────────────────────────────

@portal_login_required
def account(request):
    company = _get_portal_company(request.user)
    ams = company.account_managers.all()
    return render(request, 'portal/account.html', {
        'company': company,
        'ams':     ams,
    })
