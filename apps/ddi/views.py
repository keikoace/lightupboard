from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import DDINumber, DDIProfile, DDIRoute
from .forms import DDIProfileForm, DDINumberForm, DDIRouteForm


# ── DDI Numbers ───────────────────────────────────────────────────────────────

@login_required
def number_list(request):
    qs = DDINumber.objects.select_related('vendor', 'customer', 'destination').order_by('number')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    area = request.GET.get('area', '')
    customer_id = request.GET.get('customer', '')
    vendor_id = request.GET.get('vendor', '')
    country = request.GET.get('country', '')

    if q:
        qs = qs.filter(number__icontains=q)
    if status == 'free':
        qs = qs.filter(is_active=True, customer__isnull=True).exclude(notes__icontains='Type: Golden')
    elif status == 'assigned':
        qs = qs.filter(is_active=True, customer__isnull=False)
    elif status == 'blocked':
        qs = qs.filter(is_active=False)
    elif status == 'golden':
        qs = qs.filter(notes__icontains='Type: Golden')
    if area:
        # Template area values are E.164-style without '+' (e.g. "4133" = +41 33...).
        # Numbers may be stored as +41XXXXXXX, 41XXXXXXX, or 0XXXXXXX (national).
        # Strip the country code "41" to get the bare area digits, then match all formats.
        bare_area = area[2:] if area.startswith('41') else area  # e.g. "33"
        qs = qs.filter(
            Q(number__startswith='+' + area) |    # +41331234567
            Q(number__startswith=area) |           # 41331234567
            Q(number__startswith='0' + bare_area)  # 0331234567
        )
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if vendor_id:
        qs = qs.filter(vendor_id=vendor_id)
    if country:
        qs = qs.filter(country=country)

    from apps.core.models import Company
    customers = Company.objects.filter(role__in=['customer', 'both'], is_active=True).order_by('name')
    vendors = Company.objects.filter(role__in=['supplier', 'both'], is_active=True).order_by('name')
    countries = DDINumber.objects.values_list('country', flat=True).distinct().order_by('country')

    paginator = Paginator(qs, 100)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'ddi/number_list.html', {
        'page_obj': page,
        'q': q,
        'status': status,
        'area': area,
        'customer_id': customer_id,
        'vendor_id': vendor_id,
        'country': country,
        'customers': customers,
        'vendors': vendors,
        'countries': countries,
        'total': qs.count(),
    })


@login_required
def number_add(request):
    form = DDINumberForm(request.POST or None)
    if form.is_valid():
        num = form.save()
        messages.success(request, f'DDI number {num.number} created.')
        return redirect('ddi:number_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add DDI Number',
        'submit_label': 'Create Number',
        'cancel_url': '/ddi/numbers/',
        'breadcrumbs': [
            {'label': 'DDI Numbers', 'url': '/ddi/numbers/'},
            {'label': 'Add', 'url': ''},
        ],
    })


@login_required
def number_edit(request, pk):
    num = get_object_or_404(DDINumber, pk=pk)
    form = DDINumberForm(request.POST or None, instance=num)
    if form.is_valid():
        form.save()
        messages.success(request, f'DDI number {num.number} updated.')
        return redirect('ddi:number_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit DDI: {num.number}',
        'submit_label': 'Save Changes',
        'cancel_url': '/ddi/numbers/',
        'breadcrumbs': [
            {'label': 'DDI Numbers', 'url': '/ddi/numbers/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def number_delete(request, pk):
    num = get_object_or_404(DDINumber, pk=pk)
    if request.method == 'POST':
        num.delete()
        messages.success(request, 'DDI number deleted.')
        return redirect('ddi:number_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': num.number,
        'cancel_url': '/ddi/numbers/',
    })


# ── DDI Profiles ──────────────────────────────────────────────────────────────

@login_required
def profile_list(request):
    profiles = DDIProfile.objects.select_related('company').order_by('name')
    return render(request, 'ddi/profile_list.html', {'profiles': profiles})


@login_required
def profile_add(request):
    form = DDIProfileForm(request.POST or None)
    if form.is_valid():
        profile = form.save()
        messages.success(request, f'Profile "{profile.name}" created.')
        return redirect('ddi:profile_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add DDI Profile',
        'submit_label': 'Create Profile',
        'cancel_url': '/ddi/profiles/',
        'breadcrumbs': [
            {'label': 'DDI Profiles', 'url': '/ddi/profiles/'},
            {'label': 'Add', 'url': ''},
        ],
    })


@login_required
def profile_edit(request, pk):
    profile = get_object_or_404(DDIProfile, pk=pk)
    form = DDIProfileForm(request.POST or None, instance=profile)
    if form.is_valid():
        form.save()
        messages.success(request, f'Profile "{profile.name}" updated.')
        return redirect('ddi:profile_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Profile: {profile.name}',
        'submit_label': 'Save Changes',
        'cancel_url': '/ddi/profiles/',
        'breadcrumbs': [
            {'label': 'DDI Profiles', 'url': '/ddi/profiles/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def profile_delete(request, pk):
    profile = get_object_or_404(DDIProfile, pk=pk)
    if request.method == 'POST':
        profile.delete()
        messages.success(request, 'Profile deleted.')
        return redirect('ddi:profile_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': profile.name,
        'warning': 'DDI numbers assigned to this profile will lose their profile assignment.',
        'cancel_url': '/ddi/profiles/',
    })


# ── DDI Routes ────────────────────────────────────────────────────────────────

@login_required
def route_list(request):
    routes = DDIRoute.objects.select_related('profile', 'supplier').order_by('profile', 'priority')
    return render(request, 'ddi/route_list.html', {'routes': routes})


@login_required
def route_add(request):
    form = DDIRouteForm(request.POST or None)
    if form.is_valid():
        route = form.save()
        messages.success(request, 'Route created.')
        return redirect('ddi:route_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add DDI Route',
        'submit_label': 'Create Route',
        'cancel_url': '/ddi/routes/',
        'breadcrumbs': [
            {'label': 'DDI Routes', 'url': '/ddi/routes/'},
            {'label': 'Add', 'url': ''},
        ],
    })


@login_required
def route_edit(request, pk):
    route = get_object_or_404(DDIRoute, pk=pk)
    form = DDIRouteForm(request.POST or None, instance=route)
    if form.is_valid():
        form.save()
        messages.success(request, 'Route updated.')
        return redirect('ddi:route_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Edit Route',
        'submit_label': 'Save Changes',
        'cancel_url': '/ddi/routes/',
        'breadcrumbs': [
            {'label': 'DDI Routes', 'url': '/ddi/routes/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def route_delete(request, pk):
    route = get_object_or_404(DDIRoute, pk=pk)
    if request.method == 'POST':
        route.delete()
        messages.success(request, 'Route deleted.')
        return redirect('ddi:route_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'{route.profile} → {route.supplier}',
        'cancel_url': '/ddi/routes/',
    })


# ── DDI Cost Base ─────────────────────────────────────────────────────────────

@login_required
def cost_base(request):
    """
    Per-DDI number: aggregate buy cost and sell revenue from CDRs,
    join to DDINumber for profile/customer info.
    """
    from apps.qos.models import CDR
    from django.db.models import Sum, Count, Q

    # All DDI numbers with their CDR totals (grouped by DNIS)
    ddi_qs = DDINumber.objects.select_related('vendor', 'customer').order_by('number')

    # Use a subquery instead of loading 200k numbers into memory
    ddi_numbers_sq = DDINumber.objects.values('number')

    cdr_agg = {}
    cdr_rows = (
        CDR.objects
        .filter(dnis__in=ddi_numbers_sq)
        .values('dnis')
        .annotate(
            minutes=Sum('sell_billed_duration_sec'),
            revenue=Sum('sell_revenue'),
            cost=Sum('buy_cost'),
        )
    )
    for r in cdr_rows:
        cdr_agg[r['dnis']] = r

    entries = []
    for num in ddi_qs:
        agg = cdr_agg.get(num.number, {})
        entries.append({
            'number':   num.number,
            'country':  num.country,
            'customer': num.customer.name if num.customer else '—',
            'vendor':   num.vendor.name if num.vendor else '—',
            'buy_rate': num.buy_rate,
            'sell_rate': num.sell_rate,
            'minutes':  round((agg.get('minutes') or 0) / 60, 1),
            'cost':     agg.get('cost') or 0,
            'revenue':  agg.get('revenue') or 0,
        })

    return render(request, 'ddi/cost_base.html', {'entries': entries})


# ── DDI Loss Analysis ─────────────────────────────────────────────────────────

@login_required
def loss_analysis(request):
    from apps.qos.models import CDR
    from django.db.models import Sum, Count, Q, F

    from_date = request.GET.get('from', '').strip()
    to_date   = request.GET.get('to', '').strip()
    group_by  = request.GET.get('group', 'number')
    has_run   = bool(from_date or to_date)
    rows      = []

    if has_run:
        qs = CDR.objects.filter(dnis__in=DDINumber.objects.values('number'))

        if from_date:
            qs = qs.filter(start_time__date__gte=from_date)
        if to_date:
            qs = qs.filter(start_time__date__lte=to_date)

        if group_by == 'customer':
            agg = qs.values('customer__name').annotate(
                label=F('customer__name'),
                minutes=Sum('sell_billed_duration_sec'),
                cost=Sum('buy_cost'),
                revenue=Sum('sell_revenue'),
            ).order_by('cost')
        elif group_by == 'profile':
            # DDI profile — map dnis → profile via DDINumber
            agg = qs.values('dnis').annotate(
                label=F('dnis'),
                minutes=Sum('sell_billed_duration_sec'),
                cost=Sum('buy_cost'),
                revenue=Sum('sell_revenue'),
            ).order_by('cost')
        else:
            agg = qs.values('dnis').annotate(
                label=F('dnis'),
                minutes=Sum('sell_billed_duration_sec'),
                cost=Sum('buy_cost'),
                revenue=Sum('sell_revenue'),
            ).order_by('cost')

        from decimal import Decimal
        for r in agg:
            mins    = round((r['minutes'] or 0) / 60, 1)
            cost    = r['cost'] or Decimal('0')
            revenue = r['revenue'] or Decimal('0')
            loss    = revenue - cost
            if loss >= 0:
                continue  # Only show losses
            loss_pct = round(float(loss / cost * 100), 1) if cost else 0
            rows.append({
                'label':    str(r.get('label') or r.get('customer__name') or r.get('dnis') or '—'),
                'minutes':  mins,
                'cost':     cost,
                'revenue':  revenue,
                'loss':     loss,
                'loss_pct': loss_pct,
            })

    return render(request, 'ddi/loss_analysis.html', {
        'rows': rows,
        'has_run': has_run,
    })
    