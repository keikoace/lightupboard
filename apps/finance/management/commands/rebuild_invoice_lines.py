"""
rebuild_invoice_lines — Rebuild CDR traffic lines for draft invoices.

Deletes existing CDR lines and regenerates them using the current
invoice_group assignments on Destination. BillableItem lines are left
untouched. Invoice totals are recalculated.

Only processes DRAFT invoices — sent/paid invoices are never modified.

Usage:
    python manage.py rebuild_invoice_lines
    python manage.py rebuild_invoice_lines --dry-run
    python manage.py rebuild_invoice_lines --invoice 1042   # single invoice by ID
"""
import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, Count

from apps.finance.models import Invoice, InvoiceLine, BillingProfile
from apps.qos.models import CDR


def _round2(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _round3(value):
    return Decimal(value).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)


def _build_cdr_lines(invoice):
    """Return list of dicts for CDR traffic lines, using current invoice_group logic."""
    period_start_dt = datetime.datetime.combine(invoice.period_start, datetime.time.min)
    period_end_dt   = datetime.datetime.combine(invoice.period_end,   datetime.time.max)
    period_label    = invoice.period_start.strftime('%Y-%m')
    currency        = invoice.currency

    base_qs = CDR.objects.filter(
        customer=invoice.company,
        start_time__gte=period_start_dt,
        start_time__lte=period_end_dt,
        sell_billed_duration_sec__gt=0,
    )

    lines = []
    sort  = 0

    # Grouped destinations
    for row in (
        base_qs
        .filter(destination__invoice_group__gt='')
        .values('destination__invoice_group')
        .annotate(total_seconds=Sum('sell_billed_duration_sec'), total_revenue=Sum('sell_revenue'))
        .order_by('destination__invoice_group')
    ):
        label   = row['destination__invoice_group']
        minutes = _round3(Decimal(row['total_seconds']) / 60)
        revenue = _round2(row['total_revenue'] or 0)
        if minutes > 0:
            avg_rate = _round2(revenue / minutes)
            detail = (
                f"{label} - termination {period_label}: "
                f"{minutes} mins * {avg_rate} = {revenue} {currency}. "
                f"Total {revenue} {currency}."
            )
        else:
            detail = f"{label} - termination {period_label}: 0 mins."
        lines.append({'sort_order': sort, 'quantity': 1, 'title': 'Call Termination',
                      'description': detail, 'period_start': invoice.period_start,
                      'period_end': invoice.period_end, 'minutes': minutes,
                      'rate': avg_rate if minutes > 0 else Decimal('0'), 'amount': revenue})
        sort += 1

    # Ungrouped destinations
    for row in (
        base_qs
        .filter(destination__invoice_group='')
        .values('destination__name')
        .annotate(total_seconds=Sum('sell_billed_duration_sec'), total_revenue=Sum('sell_revenue'))
        .order_by('destination__name')
    ):
        dest_name = row['destination__name'] or 'Unknown'
        minutes   = _round3(Decimal(row['total_seconds']) / 60)
        revenue   = _round2(row['total_revenue'] or 0)
        if minutes > 0:
            avg_rate = _round2(revenue / minutes)
            detail = (
                f"{dest_name} - termination {period_label}: "
                f"{minutes} mins * {avg_rate} = {revenue} {currency}. "
                f"Total {revenue} {currency}."
            )
        else:
            detail = f"{dest_name} - termination {period_label}: 0 mins."
        lines.append({'sort_order': sort, 'quantity': 1, 'title': 'Call Termination',
                      'description': detail, 'period_start': invoice.period_start,
                      'period_end': invoice.period_end, 'minutes': minutes,
                      'rate': avg_rate if minutes > 0 else Decimal('0'), 'amount': revenue})
        sort += 1

    return lines


class Command(BaseCommand):
    help = 'Rebuild CDR lines for draft invoices using current invoice_group assignments.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would change without writing.')
        parser.add_argument('--invoice', type=int, default=None,
                            help='Rebuild a single invoice by ID.')

    def handle(self, *args, **options):
        dry_run    = options['dry_run']
        invoice_id = options['invoice']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no writes.\n'))

        qs = Invoice.objects.filter(status=Invoice.STATUS_DRAFT).select_related(
            'company', 'billing_profile'
        )
        if invoice_id:
            qs = qs.filter(pk=invoice_id)

        if not qs.exists():
            self.stdout.write('No draft invoices found.')
            return

        for invoice in qs:
            self.stdout.write(f'\n{invoice.invoice_number} — {invoice.company.name} '
                              f'({invoice.period_start} – {invoice.period_end})')

            new_lines = _build_cdr_lines(invoice)

            if not new_lines:
                self.stdout.write('  No CDR traffic — skipping.')
                continue

            # Existing non-CDR lines (BillableItem lines — keep these)
            existing_non_cdr = invoice.lines.exclude(title='Call Termination')
            kept_amount = sum(l.amount for l in existing_non_cdr)

            # Preview
            for l in new_lines:
                self.stdout.write(f'  {l["description"][:80]}')

            if not dry_run:
                with transaction.atomic():
                    # Delete old CDR lines only
                    invoice.lines.filter(title='Call Termination').delete()

                    # Fix sort_order to come after any kept lines
                    offset = existing_non_cdr.count()
                    for l in new_lines:
                        l['sort_order'] += offset
                        InvoiceLine.objects.create(invoice=invoice, **l)

                    # Recalculate totals
                    all_lines = invoice.lines.all()
                    subtotal    = _round2(sum(l.amount for l in all_lines))
                    vat_rate    = invoice.vat_rate
                    tax_amount  = _round2(subtotal * vat_rate / 100)
                    total       = _round2(subtotal + tax_amount)
                    Invoice.objects.filter(pk=invoice.pk).update(
                        subtotal=subtotal, tax_amount=tax_amount, total_amount=total
                    )
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ Rebuilt {len(new_lines)} CDR lines. New total: {total} {invoice.currency}'
                ))

        if dry_run:
            self.stdout.write(self.style.WARNING('\nDry run complete — nothing written.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nAll done.'))
