"""
Invoice generation engine.

Generates a sales invoice for a customer covering:
  1. CDR traffic (grouped by destination) for the billing period
  2. Active BillableItems whose next_billing_date falls within the period

Usage from views or management commands:
    from apps.finance.invoice_engine import generate_invoice
    invoice = generate_invoice(
        company=company,
        billing_profile=profile,
        period_start=date(2026, 4, 1),
        period_end=date(2026, 4, 30),
        issue_date=date.today(),
    )
"""
import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum, Count

from apps.core.models import Company
from apps.finance.models import BillingProfile, Invoice, InvoiceLine, BillableItem


def _round2(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _round3(value):
    return Decimal(value).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)


def generate_invoice(
    company: Company,
    billing_profile: BillingProfile,
    period_start: datetime.date,
    period_end: datetime.date,
    issue_date: datetime.date,
    include_cdrs: bool = True,
    include_billable_items: bool = True,
) -> Invoice:
    """
    Build and save a draft Invoice with all InvoiceLines.
    Raises ValueError if nothing billable is found.
    Returns the created Invoice.
    """
    from apps.qos.models import CDR

    lines_data = []   # list of dicts to become InvoiceLines
    sort = 0

    # ── 1. CDR traffic lines ───────────────────────────────────────────────
    # Group by invoice_group when set, otherwise by destination name.
    if include_cdrs:
        period_start_dt = datetime.datetime.combine(period_start, datetime.time.min)
        period_end_dt   = datetime.datetime.combine(period_end,   datetime.time.max)
        period_label    = period_start.strftime('%Y-%m')

        base_qs = CDR.objects.filter(
            customer=company,
            start_time__gte=period_start_dt,
            start_time__lte=period_end_dt,
            sell_billed_duration_sec__gt=0,
        )

        # ── 1a. Grouped destinations (invoice_group is set) ────────────────
        grouped_rows = (
            base_qs
            .filter(destination__invoice_group__gt='')
            .values('destination__invoice_group')
            .annotate(
                total_seconds=Sum('sell_billed_duration_sec'),
                total_revenue=Sum('sell_revenue'),
                call_count=Count('id'),
            )
            .order_by('destination__invoice_group')
        )

        for row in grouped_rows:
            label   = row['destination__invoice_group']
            minutes = _round3(Decimal(row['total_seconds']) / 60)
            revenue = _round2(row['total_revenue'] or 0)
            if minutes > 0:
                avg_rate = _round2(revenue / minutes)
                detail = (
                    f"{label} - termination {period_label}: "
                    f"{minutes} mins * {avg_rate} = {revenue} {billing_profile.currency}. "
                    f"Total {revenue} {billing_profile.currency}."
                )
            else:
                detail = f"{label} - termination {period_label}: 0 mins."
            lines_data.append({
                'sort_order':   sort,
                'quantity':     1,
                'title':        'Call Termination',
                'description':  detail,
                'period_start': period_start,
                'period_end':   period_end,
                'minutes':      minutes,
                'rate':         avg_rate if minutes > 0 else Decimal('0'),
                'amount':       revenue,
            })
            sort += 1

        # ── 1b. Ungrouped destinations (no invoice_group) ──────────────────
        ungrouped_rows = (
            base_qs
            .filter(destination__invoice_group='')
            .values('destination_id', 'destination__name', 'destination__prefix')
            .annotate(
                total_seconds=Sum('sell_billed_duration_sec'),
                total_revenue=Sum('sell_revenue'),
                call_count=Count('id'),
            )
            .order_by('destination__name')
        )

        for row in ungrouped_rows:
            minutes   = _round3(Decimal(row['total_seconds']) / 60)
            revenue   = _round2(row['total_revenue'] or 0)
            dest_name = row['destination__name'] or 'Unknown'
            if minutes > 0:
                avg_rate = _round2(revenue / minutes)
                detail = (
                    f"{dest_name} - termination {period_label}: "
                    f"{minutes} mins * {avg_rate} = {revenue} {billing_profile.currency}. "
                    f"Total {revenue} {billing_profile.currency}."
                )
            else:
                detail = f"{dest_name} - termination {period_label}: 0 mins."
            lines_data.append({
                'sort_order':   sort,
                'quantity':     1,
                'title':        'Call Termination',
                'description':  detail,
                'period_start': period_start,
                'period_end':   period_end,
                'minutes':      minutes,
                'rate':         avg_rate if minutes > 0 else Decimal('0'),
                'amount':       revenue,
            })
            sort += 1

    # ── 2. BillableItem lines ───────────────────────────────────────────────
    if include_billable_items:
        due_items = BillableItem.objects.filter(
            customer=company,
            is_active=True,
        ).exclude(billing_type=BillableItem.BILLING_ONE_TIME)

        # Filter to items whose next_billing_date falls within the period (or is null = always include)
        items_to_bill = [
            item for item in due_items
            if item.next_billing_date is None
            or (period_start <= item.next_billing_date <= period_end)
        ]

        for item in items_to_bill:
            amount = _round2(item.unit_price * item.quantity)
            lines_data.append({
                'sort_order':   sort,
                'quantity':     int(item.quantity),
                'title':        item.description,
                'description':  item.notes or '',
                'period_start': period_start,
                'period_end':   period_end,
                'minutes':      Decimal('0'),
                'rate':         item.unit_price,
                'amount':       amount,
            })
            sort += 1

    if not lines_data:
        raise ValueError(
            f"No billable CDR traffic or recurring items found for {company.name} "
            f"in period {period_start} – {period_end}."
        )

    # ── 3. Compute totals ───────────────────────────────────────────────────
    subtotal = _round2(sum(d['amount'] for d in lines_data))

    # VAT: use billing profile rate, but 0 if customer is vat_exempt
    vat_rate = Decimal('0') if company.vat_exempt else Decimal(str(billing_profile.vat_rate))
    tax_amount   = _round2(subtotal * vat_rate / 100)
    total_amount = _round2(subtotal + tax_amount)

    # ── 4. Create Invoice + Lines atomically ────────────────────────────────
    with transaction.atomic():
        inv_number = billing_profile.allocate_invoice_number()

        invoice = Invoice.objects.create(
            company         = company,
            billing_profile = billing_profile,
            invoice_type    = Invoice.TYPE_SALES,
            invoice_number  = str(inv_number),
            status          = Invoice.STATUS_DRAFT,
            currency        = billing_profile.currency,
            period_start    = period_start,
            period_end      = period_end,
            issue_date      = issue_date,
            due_date        = issue_date,   # caller can override after creation
            vat_rate        = vat_rate,
            subtotal        = subtotal,
            tax_amount      = tax_amount,
            total_amount    = total_amount,
            amount_paid     = Decimal('0'),
        )

        for d in lines_data:
            InvoiceLine.objects.create(invoice=invoice, **d)

        # Advance next_billing_date on billed items
        if include_billable_items:
            for item in items_to_bill:
                item.next_billing_date = _advance_billing_date(item)
                item.save(update_fields=['next_billing_date'])

    return invoice


def _advance_billing_date(item: BillableItem) -> datetime.date:
    """Compute the next billing date after this billing cycle."""
    from dateutil.relativedelta import relativedelta
    base = item.next_billing_date or datetime.date.today()
    delta_map = {
        BillableItem.BILLING_MONTHLY:     relativedelta(months=1),
        BillableItem.BILLING_QUARTERLY:   relativedelta(months=3),
        BillableItem.BILLING_HALF_YEARLY: relativedelta(months=6),
        BillableItem.BILLING_YEARLY:      relativedelta(years=1),
    }
    delta = delta_map.get(item.billing_type)
    return base + delta if delta else base
