from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import Tariff, Rate, CostBase, OriginGroup
from .forms import TariffForm, RateForm


@login_required
def supplier_rates(request):
    tariffs = Tariff.objects.filter(side='buy', is_active=True).select_related('company')
    selected_tariff = None
    rates = []
    tid = request.GET.get('tariff')
    if tid:
        selected_tariff = get_object_or_404(Tariff, pk=tid, side='buy')
        rates = selected_tariff.rates.select_related('destination').order_by('prefix')
    return render(request, 'rates/supplier_rates.html', {
        'tariffs': tariffs, 'selected_tariff': selected_tariff, 'rates': rates,
    })


@login_required
def supplier_tariffs(request):
    tariffs = Tariff.objects.filter(side='buy').select_related('company').order_by('-effective_date')
    return render(request, 'rates/tariff_list.html', {'tariffs': tariffs, 'side': 'buy'})


@login_required
def customer_rates(request):
    tariffs = Tariff.objects.filter(side='sell', is_active=True).select_related('company')
    selected_tariff = None
    rates = []
    tid = request.GET.get('tariff')
    if tid:
        selected_tariff = get_object_or_404(Tariff, pk=tid, side='sell')
        rates = selected_tariff.rates.select_related('destination').order_by('prefix')
    return render(request, 'rates/customer_rates.html', {
        'tariffs': tariffs, 'selected_tariff': selected_tariff, 'rates': rates,
    })


@login_required
def customer_tariffs(request):
    tariffs = Tariff.objects.filter(side='sell').select_related('company').order_by('-effective_date')
    return render(request, 'rates/tariff_list.html', {'tariffs': tariffs, 'side': 'sell'})


@login_required
def rate_sheet_export(request):
    tariffs = Tariff.objects.filter(side='sell', is_active=True)
    return render(request, 'rates/rate_sheet_export.html', {'tariffs': tariffs})


@login_required
def cost_base(request):
    entries = CostBase.objects.select_related('destination').order_by('-period_start')[:200]
    return render(request, 'rates/cost_base.html', {'entries': entries})


@login_required
def sell_buy_comparison(request):
    sell_tariffs = Tariff.objects.filter(side='sell', is_active=True).select_related('company').order_by('company__name', 'name')
    buy_tariffs  = Tariff.objects.filter(side='buy',  is_active=True).select_related('company').order_by('company__name', 'name')

    sell_id = request.GET.get('sell')
    buy_id  = request.GET.get('buy')
    min_margin = float(request.GET.get('min_margin', 0))
    rows = []

    if sell_id and buy_id:
        sell_tariff = get_object_or_404(Tariff, pk=sell_id, side='sell')
        buy_tariff  = get_object_or_404(Tariff, pk=buy_id,  side='buy')

        # Build lookup: prefix → buy rate
        buy_rates_qs = buy_tariff.rates.select_related('destination')
        buy_lookup   = {r.prefix: r.rate_per_minute for r in buy_rates_qs}

        for sr in sell_tariff.rates.select_related('destination').order_by('prefix'):
            buy_rate = buy_lookup.get(sr.prefix)
            if buy_rate is None:
                # Longest-prefix match
                for length in range(len(sr.prefix) - 1, 0, -1):
                    buy_rate = buy_lookup.get(sr.prefix[:length])
                    if buy_rate is not None:
                        break
            if buy_rate is None:
                continue
            margin     = sr.rate_per_minute - buy_rate
            margin_pct = float(margin / sr.rate_per_minute * 100) if sr.rate_per_minute else 0
            if margin_pct < min_margin:
                status = 'danger'
            elif margin_pct >= 20:
                status = 'success'
            else:
                status = 'warning'
            rows.append({
                'prefix':      sr.prefix,
                'destination': sr.destination.name if sr.destination else sr.prefix,
                'sell_rate':   sr.rate_per_minute,
                'buy_rate':    buy_rate,
                'margin':      margin,
                'margin_pct':  round(margin_pct, 2),
                'status':      status,
            })

    return render(request, 'rates/sell_buy_comparison.html', {
        'sell_tariffs': sell_tariffs,
        'buy_tariffs':  buy_tariffs,
        'sell_id':      sell_id,
        'buy_id':       buy_id,
        'rows':         rows,
    })


@login_required
def risk_opportunity(request):
    sell_tariffs = Tariff.objects.filter(side='sell', is_active=True).select_related('company').order_by('company__name', 'name')
    tariff_id    = request.GET.get('tariff')
    risk_pct     = float(request.GET.get('risk', 0))
    opp_pct      = float(request.GET.get('opp', 20))
    risk_rows    = []
    opp_rows     = []

    if tariff_id:
        tariff  = get_object_or_404(Tariff, pk=tariff_id, side='sell')
        cb_qs   = CostBase.objects.select_related('destination')
        cb_look = {cb.destination_id: cb.blended_cost for cb in cb_qs}

        for sr in tariff.rates.select_related('destination').order_by('prefix'):
            cost = cb_look.get(sr.destination_id)
            if cost is None:
                continue
            if cost == 0:
                continue
            margin_pct = float((sr.rate_per_minute - cost) / cost * 100)
            row = {
                'prefix':      sr.prefix,
                'destination': sr.destination.name if sr.destination else sr.prefix,
                'sell':        sr.rate_per_minute,
                'cost':        cost,
                'margin_pct':  round(margin_pct, 2),
            }
            if margin_pct < risk_pct:
                risk_rows.append(row)
            elif margin_pct > opp_pct:
                opp_rows.append(row)

    return render(request, 'rates/risk_opportunity.html', {
        'sell_tariffs': sell_tariffs,
        'tariff_id':    tariff_id,
        'risk_rows':    risk_rows,
        'opp_rows':     opp_rows,
    })


# ── Tariff CRUD ───────────────────────────────────────────────────────────────

@login_required
def tariff_add(request):
    side = request.GET.get('side', 'sell')
    form = TariffForm(request.POST or None, initial={'side': side})
    if form.is_valid():
        tariff = form.save()
        messages.success(request, f'Tariff "{tariff.name}" created.')
        return redirect('rates:supplier_tariffs' if tariff.side == 'buy' else 'rates:customer_tariffs')
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add Tariff',
        'submit_label': 'Create Tariff',
        'cancel_url': '/rates/supplier/tariffs/' if side == 'buy' else '/rates/customer/tariffs/',
        'breadcrumbs': [
            {'label': 'Rates', 'url': '#'},
            {'label': 'Add Tariff', 'url': ''},
        ],
    })


@login_required
def tariff_edit(request, pk):
    tariff = get_object_or_404(Tariff, pk=pk)
    form = TariffForm(request.POST or None, instance=tariff)
    if form.is_valid():
        form.save()
        messages.success(request, f'Tariff "{tariff.name}" updated.')
        return redirect('rates:supplier_tariffs' if tariff.side == 'buy' else 'rates:customer_tariffs')
    back = '/rates/supplier/tariffs/' if tariff.side == 'buy' else '/rates/customer/tariffs/'
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Tariff: {tariff.name}',
        'submit_label': 'Save Changes',
        'cancel_url': back,
        'breadcrumbs': [
            {'label': 'Tariffs', 'url': back},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def tariff_delete(request, pk):
    tariff = get_object_or_404(Tariff, pk=pk)
    back = '/rates/supplier/tariffs/' if tariff.side == 'buy' else '/rates/customer/tariffs/'
    if request.method == 'POST':
        tariff.delete()
        messages.success(request, 'Tariff deleted.')
        return redirect(back)
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'{tariff.name} ({tariff.company})',
        'warning': 'All rates within this tariff will also be deleted.',
        'cancel_url': back,
    })


# ── Rate CRUD ─────────────────────────────────────────────────────────────────

@login_required
def rate_add(request):
    tariff_id = request.GET.get('tariff')
    initial = {'tariff': tariff_id} if tariff_id else {}
    form = RateForm(request.POST or None, initial=initial)
    if form.is_valid():
        rate = form.save()
        messages.success(request, f'Rate for prefix {rate.prefix} created.')
        side = rate.tariff.side
        url = f'/rates/{"supplier" if side == "buy" else "customer"}/?tariff={rate.tariff.pk}'
        return redirect(url)
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': 'Add Rate',
        'submit_label': 'Create Rate',
        'cancel_url': '/rates/supplier/' if not tariff_id else f'/rates/supplier/?tariff={tariff_id}',
        'breadcrumbs': [
            {'label': 'Rates', 'url': '/rates/supplier/'},
            {'label': 'Add Rate', 'url': ''},
        ],
    })


@login_required
def rate_edit(request, pk):
    rate = get_object_or_404(Rate, pk=pk)
    form = RateForm(request.POST or None, instance=rate)
    side = rate.tariff.side
    back = f'/rates/{"supplier" if side == "buy" else "customer"}/?tariff={rate.tariff.pk}'
    if form.is_valid():
        form.save()
        messages.success(request, f'Rate for {rate.prefix} updated.')
        return redirect(back)
    return render(request, 'partials/form_page.html', {
        'form': form,
        'page_title': f'Edit Rate: {rate.prefix}',
        'submit_label': 'Save Changes',
        'cancel_url': back,
        'breadcrumbs': [
            {'label': 'Rates', 'url': back},
            {'label': 'Edit', 'url': ''},
        ],
    })


@login_required
def rate_delete(request, pk):
    rate = get_object_or_404(Rate, pk=pk)
    side = rate.tariff.side
    back = f'/rates/{"supplier" if side == "buy" else "customer"}/?tariff={rate.tariff.pk}'
    if request.method == 'POST':
        rate.delete()
        messages.success(request, 'Rate deleted.')
        return redirect(back)
    return render(request, 'partials/confirm_delete.html', {
        'object_name': f'Rate {rate.prefix} @ {rate.rate_per_minute}',
        'cancel_url': back,
    })


# ── Bulk Rate Import ──────────────────────────────────────────────────────────

import csv
import io
from decimal import Decimal, InvalidOperation
from django.utils.timezone import now

@login_required
def rate_import(request):
    """
    Two-phase import:
      GET  → show upload form (tariff selector + file input)
      POST with file, no 'confirm' → parse and show preview
      POST with 'confirm' → commit rows that passed validation
    """
    tariffs = Tariff.objects.filter(is_active=True).select_related('company').order_by('company__name', 'name')
    from apps.core.models import Destination

    # ── Phase 2: Commit ────────────────────────────────────────────────────────
    if request.method == 'POST' and 'confirm' in request.POST:
        tariff_id = request.POST.get('tariff_id')
        tariff    = get_object_or_404(Tariff, pk=tariff_id)
        rows_json = request.POST.get('rows_json', '[]')
        import json
        rows      = json.loads(rows_json)

        created = updated = skipped = 0
        eff_date = request.POST.get('effective_date') or str(now().date())

        for row in rows:
            if row.get('error'):
                skipped += 1
                continue
            dest = Destination.objects.filter(prefix=row['matched_prefix']).first() if row.get('matched_prefix') else None
            try:
                obj, is_new = Rate.objects.update_or_create(
                    tariff=tariff,
                    prefix=row['prefix'],
                    effective_date=eff_date,
                    defaults={
                        'destination': dest,
                        'rate_per_minute': Decimal(str(row['rate'])),
                        'minimum_duration_sec': int(row.get('minimum', tariff.default_billing_minimum)),
                        'billing_increment_sec': int(row.get('increment', tariff.default_billing_increment)),
                        'expiry_date': None,
                    },
                )
                if is_new:
                    created += 1
                else:
                    updated += 1
            except Exception:
                skipped += 1

        messages.success(
            request,
            f'Import complete — {created} created, {updated} updated, {skipped} skipped.'
        )
        side = tariff.side
        return redirect(f'/rates/{"supplier" if side == "buy" else "customer"}/?tariff={tariff.pk}')

    # ── Phase 1: Parse & Preview ───────────────────────────────────────────────
    preview_rows  = []
    selected_tariff = None
    effective_date  = str(now().date())
    import json as _json

    if request.method == 'POST' and 'file' in request.FILES:
        tariff_id      = request.POST.get('tariff')
        effective_date = request.POST.get('effective_date') or effective_date
        if tariff_id:
            selected_tariff = get_object_or_404(Tariff, pk=tariff_id)

        raw = request.FILES['file'].read()
        try:
            text = raw.decode('utf-8-sig')  # strip BOM if present
        except UnicodeDecodeError:
            text = raw.decode('latin-1')

        reader = csv.DictReader(io.StringIO(text))
        # Normalise headers: lowercase + strip
        reader.fieldnames = [h.strip().lower().replace(' ', '_') for h in (reader.fieldnames or [])]

        # Build prefix→destination map for matching
        dest_map = {d.prefix: d for d in Destination.objects.filter(is_active=True)}

        # Find longest-prefix match for a given prefix
        def dest_for(prefix):
            best, best_len = None, -1
            for dp, d in dest_map.items():
                if prefix.startswith(dp) and len(dp) > best_len:
                    best, best_len = d, len(dp)
            return best

        for i, row in enumerate(reader):
            if i >= 5000:   # safety cap
                break
            # Accept common column name variants
            prefix = (row.get('prefix') or row.get('code') or row.get('e164') or '').strip().lstrip('+')
            rate_raw = (row.get('rate_per_minute') or row.get('rate') or row.get('price') or '').strip()
            min_raw  = (row.get('minimum_duration_sec') or row.get('minimum') or row.get('min') or '').strip()
            incr_raw = (row.get('billing_increment_sec') or row.get('increment') or row.get('incr') or '').strip()

            error = None
            rate_val = None
            if not prefix:
                error = 'Missing prefix'
            else:
                try:
                    rate_val = Decimal(rate_raw)
                    if rate_val < 0:
                        raise ValueError
                except (InvalidOperation, ValueError):
                    error = f'Invalid rate: {rate_raw!r}'

            dest = dest_for(prefix) if prefix else None
            matched_prefix = dest.prefix if dest else None

            # Billing increments: fall back to tariff defaults
            try:
                minimum = int(min_raw) if min_raw else (selected_tariff.default_billing_minimum if selected_tariff else 1)
            except ValueError:
                minimum = selected_tariff.default_billing_minimum if selected_tariff else 1
            try:
                increment = int(incr_raw) if incr_raw else (selected_tariff.default_billing_increment if selected_tariff else 1)
            except ValueError:
                increment = selected_tariff.default_billing_increment if selected_tariff else 1

            # Check if rate already exists
            exists = False
            if selected_tariff and prefix and not error:
                exists = Rate.objects.filter(
                    tariff=selected_tariff, prefix=prefix, effective_date=effective_date
                ).exists()

            preview_rows.append({
                'prefix':          prefix,
                'rate':            str(rate_val) if rate_val is not None else rate_raw,
                'minimum':         minimum,
                'increment':       increment,
                'destination':     dest.name if dest else '—',
                'matched_prefix':  matched_prefix,
                'exists':          exists,
                'error':           error,
            })

    rows_json = _json.dumps(preview_rows)
    ok_count  = sum(1 for r in preview_rows if not r['error'])
    err_count = len(preview_rows) - ok_count

    return render(request, 'rates/rate_import.html', {
        'tariffs':          tariffs,
        'selected_tariff':  selected_tariff,
        'preview_rows':     preview_rows,
        'rows_json':        rows_json,
        'ok_count':         ok_count,
        'err_count':        err_count,
        'effective_date':   effective_date,
    })


# ── Audit Trail ───────────────────────────────────────────────────────────────

@login_required
def audit_log(request):
    from .models import AuditLog
    from django.core.paginator import Paginator

    qs = AuditLog.objects.select_related('user').order_by('-timestamp')
    obj_type = request.GET.get('type', '')
    action   = request.GET.get('action', '')
    if obj_type:
        qs = qs.filter(object_type=obj_type)
    if action:
        qs = qs.filter(action=action)

    paginator = Paginator(qs, 100)
    page      = paginator.get_page(request.GET.get('page'))

    return render(request, 'rates/audit_log.html', {
        'page_obj':  page,
        'obj_type':  obj_type,
        'action':    action,
    })



# ── Origin Groups ─────────────────────────────────────────────────────────────

@login_required
def origin_group_list(request):
    from django.db.models import Prefetch
    rate_qs = Rate.objects.select_related('tariff__company', 'destination').order_by('destination__name')
    groups = OriginGroup.objects.prefetch_related(
        'dialcodes',
        Prefetch('rates', queryset=rate_qs),
    ).order_by('name')
    return render(request, 'rates/origin_group_list.html', {'groups': groups})
