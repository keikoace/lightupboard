from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import AlertRule, AlertEvent
from .forms import AlertRuleForm
from apps.qos.models import CDR


@login_required
def unprocessed(request):
    cdrs = CDR.objects.filter(is_processed=False).select_related('customer', 'supplier').order_by('-start_time')[:200]
    return render(request, 'alerts/unprocessed.html', {'cdrs': cdrs})


@login_required
def ddi_unprocessed(request):
    from apps.ddi.models import DDINumber
    from apps.qos.models import CDR

    ddi_numbers = list(DDINumber.objects.values_list('number', flat=True))
    cdrs = (
        CDR.objects
        .filter(dnis__in=ddi_numbers, is_processed=False)
        .select_related('customer')
        .order_by('-start_time')[:200]
    )
    return render(request, 'alerts/ddi_unprocessed.html', {'cdrs': cdrs})


@login_required
def rule_list(request):
    rules = AlertRule.objects.all().order_by('name')
    return render(request, 'alerts/rule_list.html', {'rules': rules})


@login_required
def rule_add(request):
    form = AlertRuleForm(request.POST or None)
    if form.is_valid():
        rule = form.save()
        messages.success(request, f'Alert rule "{rule.name}" created.')
        return redirect('alerts:rule_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'New Alert Rule',
        'submit_label': 'Create Rule',
        'cancel_url': '/alerts/rules/',
        'breadcrumbs': [
            {'label': 'Alert Rules', 'url': '/alerts/rules/'},
            {'label': 'New Rule', 'url': ''},
        ],
    })


@login_required
def rule_edit(request, pk):
    rule = get_object_or_404(AlertRule, pk=pk)
    form = AlertRuleForm(request.POST or None, instance=rule)
    if form.is_valid():
        form.save()
        messages.success(request, f'Alert rule "{rule.name}" updated.')
        return redirect('alerts:rule_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Rule: {rule.name}',
        'submit_label': 'Save Changes',
        'cancel_url': '/alerts/rules/',
        'breadcrumbs': [
            {'label': 'Alert Rules', 'url': '/alerts/rules/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def rule_delete(request, pk):
    rule = get_object_or_404(AlertRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        messages.success(request, 'Alert rule deleted.')
        return redirect('alerts:rule_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': rule.name,
        'cancel_url': '/alerts/rules/',
    })


@login_required
def traffic_alerts(request):
    events = AlertEvent.objects.select_related('rule').order_by('-fired_at')[:200]
    return render(request, 'alerts/traffic_alerts.html', {'events': events})


@login_required
def event_action(request, pk):
    """Acknowledge or close an alert event."""
    from django.utils.timezone import now as tz_now
    event = get_object_or_404(AlertEvent, pk=pk)
    action = request.POST.get('action')
    if action == 'acknowledge' and event.status == AlertEvent.STATUS_OPEN:
        event.status = AlertEvent.STATUS_ACK
        event.acknowledged_by = request.user
        event.save(update_fields=['status', 'acknowledged_by'])
        messages.success(request, 'Alert acknowledged.')
    elif action == 'close':
        event.status = AlertEvent.STATUS_CLOSED
        event.resolved_at = tz_now()
        event.save(update_fields=['status', 'resolved_at'])
        messages.success(request, 'Alert closed.')
    return redirect('alerts:traffic_alerts')
