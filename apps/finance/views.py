import datetime
import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from .models import Invoice, InvoiceLine, Payment, TermDeal, BillVerification, BillingProfile, ExchangeRate, BillableItem, RevenueShare
from .forms import InvoiceForm, PaymentForm, TermDealForm, BillVerificationForm
from . import currency as fx
from apps.core.models import Company


# ── Finance Dashboard ─────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    recent_invoices = Invoice.objects.select_related('company').order_by('-issue_date')[:10]
    overdue = Invoice.objects.filter(status=Invoice.STATUS_OVERDUE).count()
    return render(request, 'finance/dashboard.html', {
        'recent_invoices': recent_invoices, 'overdue': overdue,
    })


# ── Invoices ──────────────────────────────────────────────────────────────────

@login_required
def invoice_list(request):
    qs = Invoice.objects.select_related('company').order_by('-issue_date')
    status = request.GET.get('status')
    q = request.GET.get('q')
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(company__name__icontains=q) | qs.filter(invoice_number__icontains=q)
    return render(request, 'finance/invoice_list.html', {'invoices': qs})


@login_required
def invoicing(request):
    invoices = Invoice.objects.filter(invoice_type='sales').select_related('company', 'billing_profile').order_by('-issue_date')
    profiles = BillingProfile.objects.filter(is_active=True)
    return render(request, 'finance/invoicing.html', {'invoices': invoices, 'profiles': profiles})


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('company', 'billing_profile').prefetch_related('lines', 'payments'),
        pk=pk,
    )
    return render(request, 'finance/invoice_detail.html', {'invoice': invoice})


@login_required
def invoice_print(request, pk):
    """Clean printable / PDF-ready view — no sidebar, no navbar."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('company', 'billing_profile').prefetch_related('lines'),
        pk=pk,
    )
    return render(request, 'finance/invoice_print.html', {'invoice': invoice})


@login_required
def invoice_generate(request):
    """
    Step 1 (GET): show form to select customer, period, billing profile.
    Step 2 (POST preview): show what will be generated — lines preview.
    Step 3 (POST confirm): actually create the invoice.
    """
    from .invoice_engine import generate_invoice

    profiles  = BillingProfile.objects.filter(is_active=True)
    customers = Company.objects.filter(role__in=['customer', 'both'], is_active=True).order_by('name')
    error     = None
    preview   = None

    if request.method == 'POST':
        company_pk   = request.POST.get('company')
        profile_pk   = request.POST.get('billing_profile')
        year         = int(request.POST.get('year',  datetime.date.today().year))
        month        = int(request.POST.get('month', datetime.date.today().month))
        include_cdrs = request.POST.get('include_cdrs') == '1'
        include_bi   = request.POST.get('include_billable_items') == '1'
        action       = request.POST.get('action', 'preview')

        try:
            company = Company.objects.get(pk=company_pk)
            profile = BillingProfile.objects.get(pk=profile_pk)

            import calendar
            period_start = datetime.date(year, month, 1)
            period_end   = datetime.date(year, month, calendar.monthrange(year, month)[1])
            issue_date   = datetime.date.today()

            if action == 'confirm':
                invoice = generate_invoice(
                    company=company,
                    billing_profile=profile,
                    period_start=period_start,
                    period_end=period_end,
                    issue_date=issue_date,
                    include_cdrs=include_cdrs,
                    include_billable_items=include_bi,
                )
                messages.success(request, f'Invoice {invoice.invoice_number} created for {company.name}.')
                return redirect('finance:invoice_detail', pk=invoice.pk)

            else:  # preview — dry run using same aggregation logic
                from apps.qos.models import CDR
                from django.db.models import Sum, Count
                from decimal import Decimal

                preview_lines = []

                if include_cdrs:
                    period_start_dt = datetime.datetime.combine(period_start, datetime.time.min)
                    period_end_dt   = datetime.datetime.combine(period_end,   datetime.time.max)
                    dest_rows = (
                        CDR.objects
                        .filter(
                            customer=company,
                            start_time__gte=period_start_dt,
                            start_time__lte=period_end_dt,
                            sell_billed_duration_sec__gt=0,
                        )
                        .values('destination__name')
                        .annotate(
                            total_seconds=Sum('sell_billed_duration_sec'),
                            total_revenue=Sum('sell_revenue'),
                            call_count=Count('id'),
                        )
                        .order_by('destination__name')
                    )
                    for row in dest_rows:
                        minutes = round(float(row['total_seconds'] or 0) / 60, 3)
                        revenue = round(float(row['total_revenue'] or 0), 2)
                        preview_lines.append({
                            'type':    'CDR',
                            'title':   'Call Termination',
                            'detail':  row['destination__name'] or 'Unknown',
                            'minutes': minutes,
                            'amount':  revenue,
                        })

                if include_bi:
                    for item in BillableItem.objects.filter(customer=company, is_active=True).exclude(
                        billing_type=BillableItem.BILLING_ONE_TIME
                    ):
                        if item.next_billing_date is None or period_start <= item.next_billing_date <= period_end:
                            preview_lines.append({
                                'type':   'Item',
                                'title':  item.description,
                                'detail': item.get_billing_type_display(),
                                'minutes': None,
                                'amount': float(item.unit_price * item.quantity),
                            })

                subtotal = sum(l['amount'] for l in preview_lines)
                vat_rate = 0 if company.vat_exempt else float(profile.vat_rate)
                tax      = round(subtotal * vat_rate / 100, 2)
                total    = round(subtotal + tax, 2)

                preview = {
                    'company':      company,
                    'profile':      profile,
                    'period_start': period_start,
                    'period_end':   period_end,
                    'lines':        preview_lines,
                    'subtotal':     subtotal,
                    'vat_rate':     vat_rate,
                    'tax':          tax,
                    'total':        total,
                    'currency':     profile.currency,
                    'year':         year,
                    'month':        month,
                    'include_cdrs': include_cdrs,
                    'include_bi':   include_bi,
                }

        except (Company.DoesNotExist, BillingProfile.DoesNotExist):
            error = 'Please select a valid customer and billing profile.'
        except ValueError as e:
            error = str(e)

    ctx = {
        'profiles':  profiles,
        'customers': customers,
        'years':     list(range(datetime.date.today().year - 2, datetime.date.today().year + 1)),
        'months':    list(range(1, 13)),
        'error':     error,
        'preview':   preview,
        'today':     datetime.date.today(),
    }
    return render(request, 'finance/invoice_generate.html', ctx)


@login_required
def invoice_add(request):
    form = InvoiceForm(request.POST or None)
    if form.is_valid():
        inv = form.save()
        messages.success(request, f'Invoice {inv.invoice_number} created.')
        return redirect('finance:invoice_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'New Invoice',
        'submit_label': 'Create Invoice',
        'cancel_url': '/finance/invoices/',
        'form_width': 'col-lg-9',
        'breadcrumbs': [
            {'label': 'Invoices', 'url': '/finance/invoices/'},
            {'label': 'New Invoice', 'url': ''},
        ],
    })


@login_required
def invoice_edit(request, pk):
    inv = get_object_or_404(Invoice, pk=pk)
    form = InvoiceForm(request.POST or None, instance=inv)
    if form.is_valid():
        form.save()
        messages.success(request, f'Invoice {inv.invoice_number} updated.')
        return redirect('finance:invoice_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Invoice {inv.invoice_number}',
        'submit_label': 'Save Changes',
        'cancel_url': '/finance/invoices/',
        'form_width': 'col-lg-9',
        'breadcrumbs': [
            {'label': 'Invoices', 'url': '/finance/invoices/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def invoice_delete(request, pk):
    inv = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        inv.delete()
        messages.success(request, 'Invoice deleted.')
        return redirect('finance:invoice_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'Invoice {inv.invoice_number}',
        'cancel_url': '/finance/invoices/',
    })


# ── Payments ──────────────────────────────────────────────────────────────────

@login_required
def payments(request):
    qs = Payment.objects.select_related('company').order_by('-payment_date')
    return render(request, 'finance/payments.html', {'payments': qs})


@login_required
def payment_add(request):
    form = PaymentForm(request.POST or None)
    if form.is_valid():
        p = form.save()
        messages.success(request, f'Payment of {p.amount} {p.currency} recorded.')
        return redirect('finance:payments')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Record Payment',
        'submit_label': 'Record Payment',
        'cancel_url': '/finance/payments/',
        'breadcrumbs': [
            {'label': 'Payments', 'url': '/finance/payments/'},
            {'label': 'Record', 'url': ''},
        ],
    })


@login_required
def payment_edit(request, pk):
    p = get_object_or_404(Payment, pk=pk)
    form = PaymentForm(request.POST or None, instance=p)
    if form.is_valid():
        form.save()
        messages.success(request, 'Payment updated.')
        return redirect('finance:payments')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Edit Payment',
        'submit_label': 'Save Changes',
        'cancel_url': '/finance/payments/',
        'breadcrumbs': [
            {'label': 'Payments', 'url': '/finance/payments/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def payment_delete(request, pk):
    p = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        p.delete()
        messages.success(request, 'Payment deleted.')
        return redirect('finance:payments')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'Payment {p.amount} {p.currency} from {p.company}',
        'cancel_url': '/finance/payments/',
    })


# ── Term Deals ────────────────────────────────────────────────────────────────

@login_required
def term_deals(request):
    deals = TermDeal.objects.select_related('company').order_by('-start_date')
    return render(request, 'finance/term_deals.html', {'deals': deals})


@login_required
def term_deal_add(request):
    form = TermDealForm(request.POST or None)
    if form.is_valid():
        deal = form.save()
        messages.success(request, f'Term deal created for {deal.company}.')
        return redirect('finance:term_deals')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'New Term Deal',
        'submit_label': 'Create Deal',
        'cancel_url': '/finance/term-deals/',
        'breadcrumbs': [
            {'label': 'Term Deals', 'url': '/finance/term-deals/'},
            {'label': 'New', 'url': ''},
        ],
    })


@login_required
def term_deal_edit(request, pk):
    deal = get_object_or_404(TermDeal, pk=pk)
    form = TermDealForm(request.POST or None, instance=deal)
    if form.is_valid():
        form.save()
        messages.success(request, 'Term deal updated.')
        return redirect('finance:term_deals')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Term Deal: {deal.destination_name}',
        'submit_label': 'Save Changes',
        'cancel_url': '/finance/term-deals/',
        'breadcrumbs': [
            {'label': 'Term Deals', 'url': '/finance/term-deals/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def term_deal_delete(request, pk):
    deal = get_object_or_404(TermDeal, pk=pk)
    if request.method == 'POST':
        deal.delete()
        messages.success(request, 'Term deal deleted.')
        return redirect('finance:term_deals')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'{deal.company} – {deal.destination_name}',
        'cancel_url': '/finance/term-deals/',
    })


# ── Bill Verification ─────────────────────────────────────────────────────────

@login_required
def bill_verification(request):
    from django.db.models import Sum
    from apps.qos.models import CDR

    verifications = BillVerification.objects.select_related('supplier').order_by('-period_start')

    # Annotate each BV with live CDR-calculated cost for display
    bv_list = []
    for bv in verifications:
        cdr_cost = CDR.objects.filter(
            supplier=bv.supplier,
            start_time__date__gte=bv.period_start,
            start_time__date__lte=bv.period_end,
            is_processed=True,
        ).aggregate(t=Sum('buy_cost'))['t'] or 0
        bv_list.append({
            'obj':             bv,
            'cdr_cost':        round(float(cdr_cost), 2),
            'variance_live':   round(float(bv.supplier_amount) - float(cdr_cost), 2),
        })

    return render(request, 'finance/bill_verification.html', {'bv_list': bv_list})


@login_required
def bill_verification_recalculate(request, pk):
    """Auto-populate our_amount from CDR buy_cost for this period/supplier."""
    from django.db.models import Sum
    from apps.qos.models import CDR

    bv = get_object_or_404(BillVerification, pk=pk)
    cdr_cost = CDR.objects.filter(
        supplier=bv.supplier,
        start_time__date__gte=bv.period_start,
        start_time__date__lte=bv.period_end,
        is_processed=True,
    ).aggregate(t=Sum('buy_cost'))['t'] or 0

    from decimal import Decimal
    bv.our_amount = Decimal(str(round(float(cdr_cost), 2)))
    bv.variance   = bv.supplier_amount - bv.our_amount
    if abs(bv.variance) < Decimal('0.01'):
        bv.status = BillVerification.STATUS_OK
    else:
        bv.status = BillVerification.STATUS_DISPUTE
    bv.save(update_fields=['our_amount', 'variance', 'status'])
    messages.success(request, f'Recalculated: our amount = {bv.our_amount}, variance = {bv.variance}.')
    return redirect('finance:bill_verification')


@login_required
def bill_verification_add(request):
    form = BillVerificationForm(request.POST or None)
    if form.is_valid():
        bv = form.save()
        messages.success(request, 'Bill verification created.')
        return redirect('finance:bill_verification')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'New Bill Verification',
        'submit_label': 'Create',
        'cancel_url': '/finance/bill-verification/',
        'breadcrumbs': [
            {'label': 'Bill Verification', 'url': '/finance/bill-verification/'},
            {'label': 'New', 'url': ''},
        ],
    })


@login_required
def bill_verification_edit(request, pk):
    bv = get_object_or_404(BillVerification, pk=pk)
    form = BillVerificationForm(request.POST or None, instance=bv)
    if form.is_valid():
        form.save()
        messages.success(request, 'Bill verification updated.')
        return redirect('finance:bill_verification')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Bill Verification: {bv.supplier}',
        'submit_label': 'Save Changes',
        'cancel_url': '/finance/bill-verification/',
        'breadcrumbs': [
            {'label': 'Bill Verification', 'url': '/finance/bill-verification/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def bill_verification_delete(request, pk):
    bv = get_object_or_404(BillVerification, pk=pk)
    if request.method == 'POST':
        bv.delete()
        messages.success(request, 'Bill verification deleted.')
        return redirect('finance:bill_verification')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'{bv.supplier} {bv.period_start}',
        'cancel_url': '/finance/bill-verification/',
    })


# ── Revenue Share ─────────────────────────────────────────────────────────────

@login_required
def revenue_share_list(request):
    shares = RevenueShare.objects.select_related('company').order_by('-is_active', 'company__name')
    return render(request, 'finance/revenue_share_list.html', {'shares': shares})


@login_required
def my_revenue_share(request):
    """
    Personal revenue share view for the logged-in AM.
    Shows their share based on managed companies' CDR profit + billable items.
    """
    from .revenue_share_calc import calculate_am_share

    today  = datetime.date.today()
    year   = int(request.GET.get('year',  today.year))
    month  = int(request.GET.get('month', today.month))

    period_start = datetime.date(year, month, 1)
    period_end   = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)

    result = calculate_am_share(request.user, period_start, period_end)

    years  = list(range(today.year - 2, today.year + 1))
    months = [(i, datetime.date(2000, i, 1).strftime('%B')) for i in range(1, 13)]

    return render(request, 'finance/revenue_share_my.html', {
        **result,
        'year': year, 'month': month,
        'period_start': period_start,
        'years': years, 'months': months,
        'am': request.user,
    })


@login_required
def all_revenue_share(request):
    """
    Superuser-only overview of all AMs' revenue shares for a period.
    """
    if not request.user.is_superuser:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Superuser access required.')

    from django.contrib.auth.models import User
    from .revenue_share_calc import calculate_am_share

    today  = datetime.date.today()
    year   = int(request.GET.get('year',  today.year))
    month  = int(request.GET.get('month', today.month))

    period_start = datetime.date(year, month, 1)
    period_end   = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)

    # All active staff users who manage at least one company
    ams = (
        User.objects
        .filter(is_active=True, managed_companies__isnull=False)
        .distinct()
        .order_by('first_name', 'username')
    )

    am_results = []
    for am in ams:
        result = calculate_am_share(am, period_start, period_end)
        if result['rows'] or result['totals']['total_share_eur']:
            am_results.append({
                'am':    am,
                'totals': result['totals'],
                'fx_date': result['fx_date'],
            })

    years  = list(range(today.year - 2, today.year + 1))
    months = [(i, datetime.date(2000, i, 1).strftime('%B')) for i in range(1, 13)]

    from .currency import latest_rates_date
    return render(request, 'finance/revenue_share_all.html', {
        'am_results':   am_results,
        'year':         year,
        'month':        month,
        'period_start': period_start,
        'years':        years,
        'months':       months,
        'fx_date':      latest_rates_date(),
    })


# ── Stubs ─────────────────────────────────────────────────────────────────────

@login_required
def gross_profit(request):
    """
    Cross-currency gross profit analysis.
    Aggregates CDRs by destination for a chosen month, converts
    sell/buy amounts to a common display currency using ECB rates.
    Flags routes where real margin turns negative after FX conversion.
    """
    from apps.qos.models import CDR
    from django.db.models import Sum, Count, F, Value
    from django.db.models.functions import TruncMonth
    from decimal import Decimal

    today = datetime.date.today()

    # ── Period filter ──────────────────────────────────────────────
    year  = int(request.GET.get('year',  today.year))
    month = int(request.GET.get('month', today.month))
    display_ccy = request.GET.get('ccy', 'EUR')  # normalisation currency

    period_start = datetime.date(year, month, 1)
    if month == 12:
        period_end = datetime.date(year + 1, 1, 1)
    else:
        period_end = datetime.date(year, month + 1, 1)

    # ── Aggregate CDRs by destination + customer ccy + supplier ccy ─
    raw = (
        CDR.objects
        .filter(
            start_time__date__gte=period_start,
            start_time__date__lt=period_end,
            sell_billed_duration_sec__gt=0,
        )
        .select_related('destination', 'customer', 'supplier')
        .values(
            'destination__id',
            'destination__name',
            'destination__prefix',
            'customer__currency',
            'supplier__currency',
        )
        .annotate(
            total_sell=Sum('sell_revenue'),
            total_buy=Sum('buy_cost'),
            total_minutes=Sum('sell_billed_duration_sec'),
            call_count=Count('id'),
        )
        .order_by('destination__name')
    )

    # ── Convert to display currency via FX ──────────────────────────
    rows = []
    totals = {'sell_display': Decimal('0'), 'buy_display': Decimal('0'),
              'margin_display': Decimal('0'), 'minutes': 0, 'calls': 0,
              'negative_count': 0}

    for r in raw:
        sell_ccy    = r['customer__currency'] or 'USD'
        buy_ccy     = r['supplier__currency'] or 'USD'
        total_sell  = r['total_sell']  or Decimal('0')
        total_buy   = r['total_buy']   or Decimal('0')
        minutes     = (r['total_minutes'] or 0) / 60

        # Convert to display currency
        sell_display = fx.convert(total_sell, sell_ccy, display_ccy) or total_sell
        buy_display  = fx.convert(total_buy,  buy_ccy,  display_ccy) or total_buy
        margin_display = sell_display - buy_display

        sell_rate = fx.get_rate(sell_ccy, display_ccy)
        buy_rate  = fx.get_rate(buy_ccy,  display_ccy)
        cross_currency = (sell_ccy != buy_ccy)
        negative = margin_display < 0

        rows.append({
            'dest_name':      r['destination__name']   or '(Unknown)',
            'dest_prefix':    r['destination__prefix'] or '',
            'sell_ccy':       sell_ccy,
            'buy_ccy':        buy_ccy,
            'total_sell':     total_sell,
            'total_buy':      total_buy,
            'sell_display':   sell_display,
            'buy_display':    buy_display,
            'margin_display': margin_display,
            'margin_pct':     (margin_display / sell_display * 100) if sell_display else Decimal('0'),
            'sell_rate':      sell_rate,
            'buy_rate':       buy_rate,
            'minutes':        round(minutes, 1),
            'call_count':     r['call_count'],
            'cross_currency': cross_currency,
            'negative':       negative,
        })

        totals['sell_display']   += sell_display
        totals['buy_display']    += buy_display
        totals['margin_display'] += margin_display
        totals['minutes']        += minutes
        totals['calls']          += r['call_count']
        if negative:
            totals['negative_count'] += 1

    totals['margin_pct'] = (
        totals['margin_display'] / totals['sell_display'] * 100
        if totals['sell_display'] else Decimal('0')
    )

    # ── Month selector data ─────────────────────────────────────────
    years  = list(range(today.year - 2, today.year + 1))
    months = [(i, datetime.date(2000, i, 1).strftime('%B')) for i in range(1, 13)]

    fx_date = fx.latest_rates_date()

    return render(request, 'finance/gross_profit.html', {
        'rows':         rows,
        'totals':       totals,
        'display_ccy':  display_ccy,
        'period_start': period_start,
        'year':         year,
        'month':        month,
        'years':        years,
        'months':       months,
        'currencies':   ['EUR', 'USD', 'CHF'],
        'fx_date':      fx_date,
    })


@login_required
def multi_invoice_email(request):
    """
    Bulk email: send all draft/approved invoices for selected customers.
    GET  – show company list with unsent invoice counts.
    POST – iterate selected customers, send each unsent invoice, return results.
    """
    from django.utils.timezone import now as tz_now
    from django.core.mail import EmailMessage
    from django.template.loader import render_to_string

    # Annotate each customer with their unsent invoice count
    unsent_statuses = [Invoice.STATUS_DRAFT]

    companies = Company.objects.filter(role__in=['customer', 'both']).order_by('name')
    company_rows = []
    for c in companies:
        unsent = Invoice.objects.filter(
            company=c,
            invoice_type=Invoice.TYPE_SALES,
            status__in=unsent_statuses,
            sent_at__isnull=True,
        ).count()
        company_rows.append({'company': c, 'unsent': unsent})

    if request.method != 'POST':
        return render(request, 'finance/multi_invoice_email.html', {
            'company_rows': company_rows,
        })

    # --- POST: send invoices ---
    selected_pks = request.POST.getlist('customers')
    subject_tpl  = request.POST.get('subject', 'Invoice from LightUpNet').strip()
    body_tpl     = request.POST.get('body', '').strip()
    attach_pdf   = bool(request.POST.get('attach_pdf'))

    results = []   # list of dicts: company, invoice_number, to_email, ok, error

    for pk in selected_pks:
        try:
            company = Company.objects.get(pk=pk)
        except Company.DoesNotExist:
            continue

        to_email = getattr(company, 'email', '') or ''
        if not to_email:
            results.append({
                'company': company.name,
                'invoice_number': '—',
                'to_email': '—',
                'ok': False,
                'error': 'No email address on record',
            })
            continue

        invoices = Invoice.objects.filter(
            company=company,
            invoice_type=Invoice.TYPE_SALES,
            status__in=unsent_statuses,
            sent_at__isnull=True,
        ).select_related('billing_profile', 'company').prefetch_related('lines')

        if not invoices.exists():
            results.append({
                'company': company.name,
                'invoice_number': '—',
                'to_email': to_email,
                'ok': None,   # None = nothing to send
                'error': 'No unsent invoices',
            })
            continue

        for invoice in invoices:
            bp_name = invoice.billing_profile.name if invoice.billing_profile else 'LightUpNet'
            subject = subject_tpl.replace('{company}', company.name).replace('{invoice}', invoice.invoice_number)
            NL = '\n'
            if body_tpl:
                text_body = body_tpl + NL + NL
            else:
                text_body = (
                    'Dear ' + company.name + ',' + NL + NL
                    + 'Please find your invoice ' + invoice.invoice_number + ' attached.' + NL + NL
                )
            text_body += (
                'Invoice number : ' + invoice.invoice_number + NL
                + 'Amount due     : ' + invoice.currency + ' ' + str(invoice.balance_due) + NL
                + 'Due date       : ' + str(invoice.due_date) + NL + NL
                + 'Kind regards,' + NL + bp_name
            )
            try:
                msg = EmailMessage(
                    subject=subject,
                    body=text_body,
                    from_email=None,
                    to=[to_email],
                )
                if attach_pdf:
                    html_body = render_to_string(
                        'finance/invoice_print.html',
                        {'invoice': invoice},
                        request=request,
                    )
                    msg.attach(
                        f'invoice_{invoice.invoice_number}.html',
                        html_body,
                        'text/html',
                    )
                msg.send(fail_silently=False)
                invoice.status  = Invoice.STATUS_SENT
                invoice.sent_at = tz_now()
                invoice.save(update_fields=['status', 'sent_at'])
                results.append({
                    'company': company.name,
                    'invoice_number': invoice.invoice_number,
                    'to_email': to_email,
                    'ok': True,
                    'error': '',
                })
            except Exception as exc:
                results.append({
                    'company': company.name,
                    'invoice_number': invoice.invoice_number,
                    'to_email': to_email,
                    'ok': False,
                    'error': str(exc),
                })

    sent_count  = sum(1 for r in results if r['ok'] is True)
    error_count = sum(1 for r in results if r['ok'] is False)

    return render(request, 'finance/multi_invoice_email.html', {
        'company_rows': company_rows,
        'results': results,
        'sent_count': sent_count,
        'error_count': error_count,
    })


@login_required
def reciprocals(request):
    """
    Bilateral gross profit view: for each carrier that is both a customer and
    supplier, show revenue from them (as customer) and cost to them (as supplier).
    """
    from apps.qos.models import CDR
    from django.db.models import Sum, Q
    from decimal import Decimal

    from_date = request.GET.get('from', '').strip()
    to_date   = request.GET.get('to', '').strip()
    has_run   = bool(from_date or to_date)
    rows      = []

    if has_run:
        qs = CDR.objects.all()
        if from_date:
            qs = qs.filter(start_time__date__gte=from_date)
        if to_date:
            qs = qs.filter(start_time__date__lte=to_date)

        # Revenue: we charged THEM as customer
        as_customer = (
            qs.values('customer__id', 'customer__name')
            .annotate(revenue=Sum('sell_revenue'))
        )
        rev_map = {r['customer__id']: (r['customer__name'], r['revenue'] or Decimal('0'))
                   for r in as_customer if r['customer__id']}

        # Cost: we paid THEM as supplier
        as_supplier = (
            qs.values('supplier__id', 'supplier__name')
            .annotate(cost=Sum('buy_cost'))
        )
        cost_map = {r['supplier__id']: (r['supplier__name'], r['cost'] or Decimal('0'))
                    for r in as_supplier if r['supplier__id']}

        # Carriers that appear on both sides
        all_ids = set(rev_map) | set(cost_map)
        for cid in sorted(all_ids, key=lambda x: (rev_map.get(x, (x,))[0] or str(x))):
            name    = (rev_map.get(cid) or cost_map.get(cid) or ('?',))[0]
            revenue = rev_map.get(cid, ('', Decimal('0')))[1]
            cost    = cost_map.get(cid, ('', Decimal('0')))[1]
            net     = revenue - cost
            rows.append({
                'name':    name,
                'revenue': revenue,
                'cost':    cost,
                'net':     net,
            })
        rows.sort(key=lambda r: r['net'])

    return render(request, 'finance/reciprocals.html', {
        'rows': rows,
        'has_run': has_run,
    })


@login_required
def maintenance(request):
    from .currency import get_rate, latest_rates_date

    latest_rate_date = latest_rates_date()

    pairs = [
        ('EUR/USD', 'EUR', 'USD'),
        ('EUR/CHF', 'EUR', 'CHF'),
        ('USD/EUR', 'USD', 'EUR'),
        ('USD/CHF', 'USD', 'CHF'),
        ('CHF/EUR', 'CHF', 'EUR'),
        ('CHF/USD', 'CHF', 'USD'),
    ]
    rate_pairs = [
        {'label': label, 'rate': get_rate(src, dst)}
        for label, src, dst in pairs
    ]

    billing_profiles = BillingProfile.objects.order_by('short_code')

    return render(request, 'finance/maintenance.html', {
        'latest_rate_date': latest_rate_date,
        'rate_pairs':       rate_pairs,
        'billing_profiles': billing_profiles,
    })


@login_required
def credit_list(request):
    from decimal import Decimal
    from django.db.models import Sum

    companies = Company.objects.filter(role__in=['customer', 'both']).order_by('name')

    entries = []
    for company in companies:
        # Outstanding = sum of balance_due on non-void, non-paid invoices
        unpaid = Invoice.objects.filter(
            company=company,
            invoice_type=Invoice.TYPE_SALES,
        ).exclude(status__in=[Invoice.STATUS_VOID]).aggregate(
            total=Sum('total_amount'),
            paid=Sum('amount_paid'),
        )
        total_invoiced = unpaid['total'] or Decimal('0')
        total_paid     = unpaid['paid']  or Decimal('0')
        outstanding    = max(total_invoiced - total_paid, Decimal('0'))
        limit          = company.credit_limit or Decimal('0')
        available      = limit - outstanding
        utilisation    = round(float(outstanding / limit * 100), 1) if limit > 0 else 0
        over_limit     = outstanding > limit > 0

        entries.append({
            'company':      company,
            'limit':        limit,
            'outstanding':  outstanding,
            'available':    available,
            'utilisation':  min(utilisation, 100),
            'over_limit':   over_limit,
        })

    return render(request, 'finance/credit_list.html', {'entries': entries})


# ── Billable Items (Customer Cart) ────────────────────────────────────────────

from apps.core.models import Company as _Company
from django import forms as _forms

class BillableItemForm(_forms.ModelForm):
    class Meta:
        model = BillableItem
        fields = ['description', 'billing_type', 'unit_price', 'quantity',
                  'currency', 'service_start', 'next_billing_date', 'is_active', 'notes']
        widgets = {
            'notes':             _forms.Textarea(attrs={'rows': 2}),
            'unit_price':        _forms.NumberInput(attrs={'step': '0.0001'}),
            'quantity':          _forms.NumberInput(attrs={'step': '0.0001'}),
            'service_start':     _forms.DateInput(attrs={'type': 'date'}),
            'next_billing_date': _forms.DateInput(attrs={'type': 'date'}),
        }


@login_required
def customer_cart(request, company_pk):
    customer = get_object_or_404(_Company, pk=company_pk)
    items = BillableItem.objects.filter(customer=customer).order_by('-is_active', 'description')
    active   = items.filter(is_active=True)
    inactive = items.filter(is_active=False)
    return render(request, 'finance/customer_cart.html', {
        'customer': customer,
        'active_items': active,
        'inactive_items': inactive,
    })


@login_required
def cart_item_add(request, company_pk):
    customer = get_object_or_404(_Company, pk=company_pk)
    form = BillableItemForm(request.POST or None, initial={'currency': customer.currency or 'USD'})
    if form.is_valid():
        item = form.save(commit=False)
        item.customer = customer
        item.save()
        messages.success(request, f'Item "{item.description}" added.')
        return redirect('finance:customer_cart', company_pk=company_pk)
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Add Item – {customer.name}',
        'submit_label': 'Add Item',
        'cancel_url': f'/finance/cart/{company_pk}/',
        'breadcrumbs': [
            {'label': 'Companies', 'url': '/setup/companies/'},
            {'label': customer.name, 'url': f'/setup/companies/{company_pk}/'},
            {'label': 'Cart', 'url': f'/finance/cart/{company_pk}/'},
            {'label': 'Add Item', 'url': ''},
        ],
    })


@login_required
def cart_item_edit(request, pk):
    item = get_object_or_404(BillableItem, pk=pk)
    form = BillableItemForm(request.POST or None, instance=item)
    if form.is_valid():
        form.save()
        messages.success(request, f'Item "{item.description}" updated.')
        return redirect('finance:customer_cart', company_pk=item.customer_id)
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Item – {item.customer.name}',
        'submit_label': 'Save Changes',
        'cancel_url': f'/finance/cart/{item.customer_id}/',
        'breadcrumbs': [
            {'label': 'Companies', 'url': '/setup/companies/'},
            {'label': item.customer.name, 'url': f'/setup/companies/{item.customer_id}/'},
            {'label': 'Cart', 'url': f'/finance/cart/{item.customer_id}/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def cart_item_delete(request, pk):
    item = get_object_or_404(BillableItem, pk=pk)
    company_pk = item.customer_id
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Item deleted.')
        return redirect('finance:customer_cart', company_pk=company_pk)
    return render(request, 'partials/confirm_delete.html', {
        'object_name': item.description,
        'cancel_url': f'/finance/cart/{company_pk}/',
    })


# ── Currency ──────────────────────────────────────────────────────────────────

@login_required
def currency_rates(request):
    """
    Standalone currency page: today's rates, 30-day history, live JS converter.
    """
    today = datetime.date.today()
    latest_date = fx.latest_rates_date()

    # Build rate matrix for display
    currencies = ['EUR', 'USD', 'CHF']
    matrix = []
    for src in currencies:
        row = {'from': src, 'rates': []}
        for dst in currencies:
            if src == dst:
                row['rates'].append({'to': dst, 'rate': None, 'same': True})
            else:
                r = fx.get_rate(src, dst)
                row['rates'].append({'to': dst, 'rate': r, 'same': False})
        matrix.append(row)

    # History: last 30 days — group by date, derive all 6 cross-rate pairs
    from django.db.models import Max
    from decimal import Decimal as D

    history_qs = (
        ExchangeRate.objects
        .filter(base_currency='EUR')
        .order_by('-date')[:60]  # 30 days × 2 currencies
    )

    # Group raw ECB rows by date: {date: {currency: rate}}
    raw_by_date = {}
    for row in history_qs:
        raw_by_date.setdefault(row.date, {})
        raw_by_date[row.date][row.currency] = row.rate

    # Build history with all 6 pairs derived via EUR base
    history = []
    for d, v in sorted(raw_by_date.items(), reverse=True):
        eur_usd = v.get('USD')   # units of USD per 1 EUR
        eur_chf = v.get('CHF')   # units of CHF per 1 EUR
        entry = {
            'date':    d,
            'EUR_USD': eur_usd,
            'EUR_CHF': eur_chf,
            'USD_EUR': (D('1') / D(str(eur_usd))).quantize(D('0.000001')) if eur_usd else None,
            'CHF_EUR': (D('1') / D(str(eur_chf))).quantize(D('0.000001')) if eur_chf else None,
            'USD_CHF': (D(str(eur_chf)) / D(str(eur_usd))).quantize(D('0.000001')) if (eur_usd and eur_chf) else None,
            'CHF_USD': (D(str(eur_usd)) / D(str(eur_chf))).quantize(D('0.000001')) if (eur_usd and eur_chf) else None,
        }
        history.append(entry)
    history = history[:30]

    # All pairs for the JS converter — define display order
    all_pairs = [
        ('EUR', 'USD'), ('EUR', 'CHF'),
        ('USD', 'EUR'), ('USD', 'CHF'),
        ('CHF', 'EUR'), ('CHF', 'USD'),
    ]

    # JSON for the JS converter widget
    pairs_json = json.dumps(fx.all_pairs_for_date())

    return render(request, 'finance/currency.html', {
        'matrix': matrix,
        'history': history,
        'all_pairs': all_pairs,
        'latest_date': latest_date,
        'currencies': currencies,
        'pairs_json': pairs_json,
        'today': today,
    })


# ── Invoice Send ──────────────────────────────────────────────────────────────

@login_required
def invoice_send(request, pk):
    """
    Send an invoice by email as an HTML attachment.
    Marks the invoice status=sent and records sent_at.
    """
    from django.utils.timezone import now as tz_now
    from django.core.mail import EmailMessage
    from django.template.loader import render_to_string

    invoice = get_object_or_404(
        Invoice.objects.select_related('company', 'billing_profile').prefetch_related('lines'),
        pk=pk,
    )

    if request.method != 'POST':
        # Show confirmation page
        to_email = (
            invoice.company.email
            if hasattr(invoice.company, 'email') else ''
        )
        return render(request, 'finance/invoice_send_confirm.html', {
            'invoice': invoice,
            'to_email': to_email,
        })

    to_email  = request.POST.get('to_email', '').strip()
    cc_email  = request.POST.get('cc_email', '').strip()
    body_note = request.POST.get('note', '').strip()

    if not to_email:
        messages.error(request, 'Recipient email is required.')
        return redirect('finance:invoice_send', pk=pk)

    # Render invoice as HTML for attachment
    html_body = render_to_string('finance/invoice_print.html', {'invoice': invoice}, request=request)

    subject = f'Invoice {invoice.invoice_number} from {invoice.billing_profile.name if invoice.billing_profile else "LightUpNet"}'
    text_body = (
        f'Dear {invoice.company.name},\n\n'
        f'Please find your invoice {invoice.invoice_number} attached.\n\n'
        f'{("Note: " + body_note + chr(10) + chr(10)) if body_note else ""}'
        f'Amount due: {invoice.currency} {invoice.balance_due:.2f}\n'
        f'Due date:   {invoice.due_date}\n\n'
        f'Kind regards,\n'
        f'{invoice.billing_profile.name if invoice.billing_profile else "LightUpNet"}'
    )

    try:
        msg = EmailMessage(
            subject=subject,
            body=text_body,
            from_email=None,   # uses DEFAULT_FROM_EMAIL from settings
            to=[to_email],
            cc=[cc_email] if cc_email else [],
        )
        # Attach as HTML file
        msg.attach(
            f'invoice_{invoice.invoice_number}.html',
            html_body,
            'text/html',
        )
        msg.send(fail_silently=False)

        invoice.status  = Invoice.STATUS_SENT
        invoice.sent_at = tz_now()
        invoice.save(update_fields=['status', 'sent_at'])
        messages.success(request, f'Invoice {invoice.invoice_number} sent to {to_email}.')
    except Exception as exc:
        messages.error(request, f'Email failed: {exc}')

    return redirect('finance:invoice_detail', pk=pk)
