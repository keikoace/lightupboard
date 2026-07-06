from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
import datetime
from apps.core.models import Company, Switch, Destination, DisconnectCause, Trunk
from apps.core.forms import CompanyForm, SwitchForm, DestinationForm, DisconnectCauseForm, TrunkForm, PortalUserForm


# ── Users ────────────────────────────────────────────────────────────────────

@login_required
def user_list(request):
    users = User.objects.all().order_by('username')
    return render(request, 'setup/user_list.html', {'users': users})


# ── Companies ─────────────────────────────────────────────────────────────────

@login_required
def company_list(request):
    qs = Company.objects.prefetch_related('account_managers').all()
    q    = request.GET.get('q')
    role = request.GET.get('role')
    am   = request.GET.get('am')
    if q:
        qs = qs.filter(name__icontains=q)
    if role:
        qs = qs.filter(role=role)
    if am == 'me':
        qs = qs.filter(account_managers=request.user)
    elif am == 'none':
        qs = qs.filter(account_managers__isnull=True)
    elif am:
        qs = qs.filter(account_managers__pk=am)
    all_users = User.objects.filter(is_active=True).order_by('first_name', 'username')
    return render(request, 'setup/company_list.html', {'companies': qs, 'all_users': all_users})


@login_required
def company_detail(request, pk):
    company = get_object_or_404(Company, pk=pk)
    return render(request, 'setup/company_detail.html', {'company': company})


@login_required
def company_profile(request, pk):
    from apps.qos.models import CDR, MinuteSummary
    from apps.rates.models import Tariff, Rate
    from apps.ddi.models import DDINumber
    from apps.finance.models import Invoice, BillableItem, TermDeal

    company = get_object_or_404(Company, pk=pk)
    now = timezone.now()
    last_30 = now - datetime.timedelta(days=30)
    last_90 = now - datetime.timedelta(days=90)

    # ── Traffic stats (last 30 days) ──────────────────────────────────────────
    cdr_as_customer = CDR.objects.filter(customer=company, start_time__gte=last_30)
    cdr_as_supplier = CDR.objects.filter(supplier=company, start_time__gte=last_30)

    customer_stats = cdr_as_customer.aggregate(
        total_calls=Count('id'),
        total_minutes=Sum('sell_billed_duration_sec'),
        total_revenue=Sum('sell_revenue'),
        avg_sell_rate=Avg('sell_rate'),
    )
    supplier_stats = cdr_as_supplier.aggregate(
        total_calls=Count('id'),
        total_minutes=Sum('sell_billed_duration_sec'),
        total_cost=Sum('buy_cost'),
        avg_buy_rate=Avg('buy_rate'),
    )

    # Convert seconds → minutes
    cust_min = (customer_stats['total_minutes'] or 0) / 60
    supp_min = (supplier_stats['total_minutes'] or 0) / 60

    # ── Top destinations as customer (by minutes) ─────────────────────────────
    top_dest_customer = (
        cdr_as_customer
        .filter(destination__isnull=False)
        .values('destination__name', 'destination__prefix')
        .annotate(
            minutes=Sum('sell_billed_duration_sec'),
            calls=Count('id'),
            revenue=Sum('sell_revenue'),
        )
        .order_by('-minutes')[:15]
    )
    # Convert seconds → minutes in the queryset results
    top_dest_customer = [
        {**d, 'minutes': round((d['minutes'] or 0) / 60, 1)}
        for d in top_dest_customer
    ]

    # ── Top destinations as supplier (by minutes) ─────────────────────────────
    top_dest_supplier = (
        cdr_as_supplier
        .filter(destination__isnull=False)
        .values('destination__name', 'destination__prefix')
        .annotate(
            minutes=Sum('sell_billed_duration_sec'),
            calls=Count('id'),
            cost=Sum('buy_cost'),
        )
        .order_by('-minutes')[:15]
    )
    top_dest_supplier = [
        {**d, 'minutes': round((d['minutes'] or 0) / 60, 1)}
        for d in top_dest_supplier
    ]

    # ── Tariffs ───────────────────────────────────────────────────────────────
    sell_tariffs = Tariff.objects.filter(company=company, side='sell', is_active=True).prefetch_related('rates')
    buy_tariffs  = Tariff.objects.filter(company=company, side='buy',  is_active=True).prefetch_related('rates')

    # ── DIDs ──────────────────────────────────────────────────────────────────
    dids_assigned = DDINumber.objects.filter(customer=company).select_related('destination', 'vendor')
    dids_provided = DDINumber.objects.filter(vendor=company).select_related('destination', 'customer')

    # ── Finance ───────────────────────────────────────────────────────────────
    recent_invoices  = Invoice.objects.filter(company=company).order_by('-issue_date')[:10]
    billable_items   = BillableItem.objects.filter(customer=company, is_active=True)
    term_deals       = TermDeal.objects.filter(company=company, is_active=True)

    # ── Recent CDRs (last 20 for each side) ───────────────────────────────────
    recent_cdr_customer = CDR.objects.filter(customer=company).select_related('destination', 'supplier').order_by('-start_time')[:20]
    recent_cdr_supplier = CDR.objects.filter(supplier=company).select_related('destination', 'customer').order_by('-start_time')[:20]

    ctx = {
        'company': company,
        'customer_stats': {
            'calls': customer_stats['total_calls'] or 0,
            'minutes': round(cust_min, 1),
            'revenue': customer_stats['total_revenue'] or 0,
            'avg_rate': customer_stats['avg_sell_rate'] or 0,
        },
        'supplier_stats': {
            'calls': supplier_stats['total_calls'] or 0,
            'minutes': round(supp_min, 1),
            'cost': supplier_stats['total_cost'] or 0,
            'avg_rate': supplier_stats['avg_buy_rate'] or 0,
        },
        'top_dest_customer': top_dest_customer,
        'top_dest_supplier': top_dest_supplier,
        'sell_tariffs': sell_tariffs,
        'buy_tariffs': buy_tariffs,
        'dids_assigned': dids_assigned,
        'dids_provided': dids_provided,
        'recent_invoices': recent_invoices,
        'billable_items': billable_items,
        'term_deals': term_deals,
        'recent_cdr_customer': recent_cdr_customer,
        'recent_cdr_supplier': recent_cdr_supplier,
    }
    return render(request, 'setup/company_profile.html', ctx)


@login_required
def company_add(request):
    form = CompanyForm(request.POST or None)
    if form.is_valid():
        company = form.save()
        messages.success(request, f'Company "{company.name}" created.')
        return redirect('setup:company_detail', pk=company.pk)
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add Company',
        'submit_label': 'Create Company',
        'cancel_url': '/setup/companies/',
        'breadcrumbs': [
            {'label': 'Companies', 'url': '/setup/companies/'},
            {'label': 'Add Company', 'url': ''},
        ],
    })


@login_required
def company_edit(request, pk):
    company = get_object_or_404(Company, pk=pk)
    form = CompanyForm(request.POST or None, instance=company)
    if form.is_valid():
        form.save()
        messages.success(request, f'Company "{company.name}" updated.')
        return redirect('setup:company_detail', pk=company.pk)
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit {company.name}',
        'submit_label': 'Save Changes',
        'cancel_url': f'/setup/companies/{pk}/',
        'breadcrumbs': [
            {'label': 'Companies', 'url': '/setup/companies/'},
            {'label': company.name, 'url': f'/setup/companies/{pk}/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def company_delete(request, pk):
    company = get_object_or_404(Company, pk=pk)
    if request.method == 'POST':
        name = company.name
        company.delete()
        messages.success(request, f'Company "{name}" deleted.')
        return redirect('setup:company_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': company.name,
        'warning': 'This will also remove all associated tariffs, invoices, and DDI numbers.',
        'cancel_url': f'/setup/companies/{pk}/',
    })


# ── Portal Users ─────────────────────────────────────────────────────────────

@login_required
def portal_user_list(request):
    """All Django users that are linked to at least one company as portal users."""
    from django.contrib.auth.models import User
    users = (
        User.objects
        .filter(customer_companies__isnull=False)
        .prefetch_related('customer_companies')
        .distinct()
        .order_by('username')
    )
    return render(request, 'setup/portal_user_list.html', {'portal_users': users})


@login_required
def portal_user_add(request):
    from django.contrib.auth.models import User
    form = PortalUserForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        user = User.objects.create_user(
            username=d['username'],
            password=d['password'],
            email=d.get('email', ''),
            first_name=d.get('first_name', ''),
            last_name=d.get('last_name', ''),
        )
        d['company'].portal_users.add(user)
        messages.success(request, f'Portal user "{user.username}" created and linked to {d["company"]}.')
        return redirect('setup:portal_user_list')
    return render(request, 'setup/portal_user_form.html', {
        'form': form, 'title': 'Add Portal User',
    })


@login_required
def portal_user_edit(request, pk):
    from django.contrib.auth.models import User
    user = get_object_or_404(User, pk=pk)
    current_company = (
        Company.objects.filter(portal_users=user).first()
    )
    initial = {'company': current_company} if current_company else {}
    form = PortalUserForm(request.POST or None, user=user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        user.username   = d['username']
        user.first_name = d.get('first_name', '')
        user.last_name  = d.get('last_name', '')
        user.email      = d.get('email', '')
        if d.get('password'):
            user.set_password(d['password'])
        user.save()
        # Re-link company: remove from all current companies, add to selected
        for co in Company.objects.filter(portal_users=user):
            co.portal_users.remove(user)
        d['company'].portal_users.add(user)
        messages.success(request, f'Portal user "{user.username}" updated.')
        return redirect('setup:portal_user_list')
    return render(request, 'setup/portal_user_form.html', {
        'form': form, 'title': 'Edit Portal User', 'edit_user': user,
    })


@login_required
def portal_user_revoke(request, pk):
    from django.contrib.auth.models import User
    user = get_object_or_404(User, pk=pk)

    # Safety: never allow deleting staff or superuser accounts here
    can_delete = not (user.is_staff or user.is_superuser)

    if request.method == 'POST':
        for co in Company.objects.filter(portal_users=user):
            co.portal_users.remove(user)
        delete_user = request.POST.get('delete_user') == '1' and can_delete
        if delete_user:
            user.delete()
            messages.success(request, f'Portal user "{user.username}" deleted.')
        else:
            messages.success(request, f'Portal access revoked for "{user.username}" (account kept).')
        return redirect('setup:portal_user_list')
    companies = Company.objects.filter(portal_users=user)
    return render(request, 'setup/portal_user_revoke.html', {
        'portal_user': user, 'companies': companies, 'can_delete': can_delete,
    })


# ── Trunks ────────────────────────────────────────────────────────────────────

@login_required
def trunk_add(request, company_pk):
    company = get_object_or_404(Company, pk=company_pk)
    form = TrunkForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        trunk = form.save(commit=False)
        trunk.company = company
        trunk.save()
        messages.success(request, f'Trunk "{trunk.name}" added.')
        return redirect('setup:company_detail', pk=company_pk)
    return render(request, 'setup/trunk_form.html', {
        'form': form, 'company': company, 'title': 'Add Trunk',
    })


@login_required
def trunk_edit(request, company_pk, pk):
    company = get_object_or_404(Company, pk=company_pk)
    trunk   = get_object_or_404(Trunk, pk=pk, company=company)
    form = TrunkForm(request.POST or None, instance=trunk)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Trunk "{trunk.name}" updated.')
        return redirect('setup:company_detail', pk=company_pk)
    return render(request, 'setup/trunk_form.html', {
        'form': form, 'company': company, 'trunk': trunk, 'title': 'Edit Trunk',
    })


@login_required
def trunk_delete(request, company_pk, pk):
    company = get_object_or_404(Company, pk=company_pk)
    trunk   = get_object_or_404(Trunk, pk=pk, company=company)
    if request.method == 'POST':
        name = trunk.name
        trunk.delete()
        messages.success(request, f'Trunk "{name}" deleted.')
        return redirect('setup:company_detail', pk=company_pk)
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'{company.name} / {trunk.name}',
        'cancel_url': f'/setup/companies/{company_pk}/',
    })


# ── Switches ──────────────────────────────────────────────────────────────────

@login_required
def switch_list(request):
    switches = Switch.objects.all()
    return render(request, 'setup/switch_list.html', {'switches': switches})


@login_required
def switch_add(request):
    form = SwitchForm(request.POST or None)
    if form.is_valid():
        sw = form.save()
        messages.success(request, f'Switch "{sw.name}" created.')
        return redirect('setup:switch_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add Switch',
        'submit_label': 'Create Switch',
        'cancel_url': '/setup/switches/',
        'breadcrumbs': [
            {'label': 'Switches', 'url': '/setup/switches/'},
            {'label': 'Add Switch', 'url': ''},
        ],
    })


@login_required
def switch_edit(request, pk):
    sw = get_object_or_404(Switch, pk=pk)
    form = SwitchForm(request.POST or None, instance=sw)
    if form.is_valid():
        form.save()
        messages.success(request, f'Switch "{sw.name}" updated.')
        return redirect('setup:switch_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Switch: {sw.name}',
        'submit_label': 'Save Changes',
        'cancel_url': '/setup/switches/',
        'breadcrumbs': [
            {'label': 'Switches', 'url': '/setup/switches/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def switch_delete(request, pk):
    sw = get_object_or_404(Switch, pk=pk)
    if request.method == 'POST':
        sw.delete()
        messages.success(request, f'Switch deleted.')
        return redirect('setup:switch_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': sw.name,
        'cancel_url': '/setup/switches/',
    })


# ── Destinations ──────────────────────────────────────────────────────────────

@login_required
def destination_list(request):
    qs = Destination.objects.all()
    q = request.GET.get('q')
    country = request.GET.get('country')
    if q:
        qs = qs.filter(name__icontains=q) | qs.filter(prefix__icontains=q)
    if country:
        qs = qs.filter(country__icontains=country)
    return render(request, 'setup/destination_list.html', {'destinations': qs})


@login_required
def destination_add(request):
    form = DestinationForm(request.POST or None)
    if form.is_valid():
        dest = form.save()
        messages.success(request, f'Destination "{dest.name}" created.')
        return redirect('setup:destination_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add Destination',
        'submit_label': 'Create Destination',
        'cancel_url': '/setup/destinations/',
        'breadcrumbs': [
            {'label': 'Destinations', 'url': '/setup/destinations/'},
            {'label': 'Add', 'url': ''},
        ],
    })


@login_required
def destination_edit(request, pk):
    dest = get_object_or_404(Destination, pk=pk)
    form = DestinationForm(request.POST or None, instance=dest)
    if form.is_valid():
        form.save()
        messages.success(request, f'Destination "{dest.name}" updated.')
        return redirect('setup:destination_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Destination: {dest.name}',
        'submit_label': 'Save Changes',
        'cancel_url': '/setup/destinations/',
        'breadcrumbs': [
            {'label': 'Destinations', 'url': '/setup/destinations/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def destination_delete(request, pk):
    dest = get_object_or_404(Destination, pk=pk)
    if request.method == 'POST':
        dest.delete()
        messages.success(request, 'Destination deleted.')
        return redirect('setup:destination_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'{dest.prefix} – {dest.name}',
        'cancel_url': '/setup/destinations/',
    })


# ── Disconnect Causes ─────────────────────────────────────────────────────────

@login_required
def disc_cause_list(request):
    causes = DisconnectCause.objects.all()
    return render(request, 'setup/disc_cause_list.html', {'causes': causes})


@login_required
def disc_cause_add(request):
    form = DisconnectCauseForm(request.POST or None)
    if form.is_valid():
        cause = form.save()
        messages.success(request, f'Disconnect cause {cause.code} created.')
        return redirect('setup:disc_cause_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add Disconnect Cause',
        'submit_label': 'Create',
        'cancel_url': '/setup/disconnect-causes/',
        'breadcrumbs': [
            {'label': 'Disconnect Causes', 'url': '/setup/disconnect-causes/'},
            {'label': 'Add', 'url': ''},
        ],
    })


@login_required
def disc_cause_edit(request, pk):
    cause = get_object_or_404(DisconnectCause, pk=pk)
    form = DisconnectCauseForm(request.POST or None, instance=cause)
    if form.is_valid():
        form.save()
        messages.success(request, f'Disconnect cause {cause.code} updated.')
        return redirect('setup:disc_cause_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Cause {cause.code}: {cause.name}',
        'submit_label': 'Save Changes',
        'cancel_url': '/setup/disconnect-causes/',
        'breadcrumbs': [
            {'label': 'Disconnect Causes', 'url': '/setup/disconnect-causes/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def disc_cause_delete(request, pk):
    cause = get_object_or_404(DisconnectCause, pk=pk)
    if request.method == 'POST':
        cause.delete()
        messages.success(request, 'Disconnect cause deleted.')
        return redirect('setup:disc_cause_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'{cause.code} – {cause.name}',
        'cancel_url': '/setup/disconnect-causes/',
    })


# ── Interconnects ─────────────────────────────────────────────────────────────

@login_required
def interconnect_list(request):
    companies = Company.objects.filter(role__in=['supplier', 'both'])
    return render(request, 'setup/interconnect_list.html', {'companies': companies})


# ── Tickets ───────────────────────────────────────────────────────────────────

from apps.setup.models import Ticket


@login_required
def ticket_list(request):
    status_filter = request.GET.get('status', '')
    tickets = Ticket.objects.select_related('company', 'created_by').order_by('-created_at')
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    return render(request, 'setup/ticket_list.html', {
        'tickets':       tickets,
        'status_filter': status_filter,
        'companies':     Company.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def ticket_create(request):
    if request.method == 'POST':
        subject     = request.POST.get('subject', '').strip()
        company_pk  = request.POST.get('company', '')
        priority    = request.POST.get('priority', Ticket.PRIORITY_MEDIUM)
        description = request.POST.get('description', '').strip()
        if not subject:
            messages.error(request, 'Subject is required.')
            return redirect('setup:ticket_list')
        company = None
        if company_pk:
            try:
                company = Company.objects.get(pk=company_pk)
            except Company.DoesNotExist:
                pass
        Ticket.objects.create(
            subject=subject,
            company=company,
            priority=priority,
            description=description,
            created_by=request.user,
            status=Ticket.STATUS_OPEN,
        )
        messages.success(request, 'Ticket created.')
    return redirect('setup:ticket_list')


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related('company', 'created_by'), pk=pk)
    return render(request, 'setup/ticket_detail.html', {
        'ticket':    ticket,
        'companies': Company.objects.filter(is_active=True).order_by('name'),
    })


@login_required
def ticket_update(request, pk):
    """Update ticket status / priority / description via POST."""
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'status':
            new_status = request.POST.get('status', '')
            if new_status in dict(Ticket.STATUS_CHOICES):
                from django.utils import timezone
                ticket.status = new_status
                if new_status == Ticket.STATUS_CLOSED and not ticket.resolved_at:
                    ticket.resolved_at = timezone.now()
                elif new_status != Ticket.STATUS_CLOSED:
                    ticket.resolved_at = None
                ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])
                messages.success(request, f'Ticket #{ticket.pk} marked {ticket.get_status_display()}.')
        elif action == 'edit':
            ticket.subject     = request.POST.get('subject', ticket.subject).strip() or ticket.subject
            ticket.priority    = request.POST.get('priority', ticket.priority)
            ticket.description = request.POST.get('description', ticket.description)
            company_pk = request.POST.get('company', '')
            if company_pk:
                try:
                    ticket.company = Company.objects.get(pk=company_pk)
                except Company.DoesNotExist:
                    pass
            else:
                ticket.company = None
            ticket.save()
            messages.success(request, 'Ticket updated.')
    return redirect('setup:ticket_detail', pk=pk)
