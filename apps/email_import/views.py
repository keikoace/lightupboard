from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import VendorEmailRule, RateImportLog
from .forms import VendorEmailRuleForm


@login_required
def rule_list(request):
    rules = VendorEmailRule.objects.select_related('tariff__company').all()
    recent_logs = RateImportLog.objects.select_related('rule').order_by('-processed_at')[:20]
    return render(request, 'email_import/rule_list.html', {
        'rules': rules,
        'recent_logs': recent_logs,
    })


@login_required
def rule_add(request):
    form = VendorEmailRuleForm(request.POST or None)
    if form.is_valid():
        rule = form.save()
        messages.success(request, f'Rule "{rule.name}" created.')
        return redirect('email_import:rule_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add Email Import Rule',
        'submit_label': 'Create Rule',
        'cancel_url': '/email-import/',
        'breadcrumbs': [
            {'label': 'Email Import', 'url': '/email-import/'},
            {'label': 'Add Rule', 'url': ''},
        ],
    })


@login_required
def rule_edit(request, pk):
    rule = get_object_or_404(VendorEmailRule, pk=pk)
    form = VendorEmailRuleForm(request.POST or None, instance=rule)
    if form.is_valid():
        form.save()
        messages.success(request, f'Rule "{rule.name}" updated.')
        return redirect('email_import:rule_list')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Rule: {rule.name}',
        'submit_label': 'Save Changes',
        'cancel_url': '/email-import/',
        'breadcrumbs': [
            {'label': 'Email Import', 'url': '/email-import/'},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def rule_delete(request, pk):
    rule = get_object_or_404(VendorEmailRule, pk=pk)
    if request.method == 'POST':
        name = rule.name
        rule.delete()
        messages.success(request, f'Rule "{name}" deleted.')
        return redirect('email_import:rule_list')
    return render(request, 'partials/confirm_delete.html', {
        'object_name': rule.name,
        'cancel_url': '/email-import/',
    })


@login_required
def log_detail(request, pk):
    log = get_object_or_404(RateImportLog.objects.select_related('rule'), pk=pk)
    return render(request, 'email_import/log_detail.html', {'log': log})


@login_required
def run_now(request):
    """Manually trigger check_rate_emails from the UI."""
    if request.method == 'POST':
        from django.core.management import call_command
        import io
        out = io.StringIO()
        try:
            call_command('check_rate_emails', stdout=out)
            output = out.getvalue()
            messages.success(request, 'Email check completed.')
        except Exception as e:
            output = str(e)
            messages.error(request, f'Error: {e}')
        return render(request, 'email_import/run_result.html', {'output': output})
    return redirect('email_import:rule_list')
