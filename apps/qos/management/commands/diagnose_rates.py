"""
Quick diagnostic: show how CDRs are rated after process_cdrs.
Usage: py manage.py diagnose_rates
"""
from django.core.management.base import BaseCommand
from apps.qos.models import CDR
from apps.rates.models import Tariff, Rate
from django.db.models import Count, Sum, Q


class Command(BaseCommand):
    help = 'Diagnose CDR rating coverage.'

    def handle(self, *args, **options):
        w = self.stdout.write

        # ── Tariff setup ──────────────────────────────────────────────────────
        w('\n=== Active Tariffs ===')
        for t in Tariff.objects.filter(is_active=True).select_related('company'):
            rate_count = Rate.objects.filter(tariff=t).count()
            w(f'  [{t.side.upper()}] {t.company.name} – "{t.name}"  '
              f'(id={t.pk}, eff={t.effective_date}, rates={rate_count})')

        # ── CDR processing summary ────────────────────────────────────────────
        total      = CDR.objects.count()
        processed  = CDR.objects.filter(is_processed=True).count()
        unprocessed= total - processed
        w(f'\n=== CDR Processing ===')
        w(f'  Total CDRs      : {total:,}')
        w(f'  Processed       : {processed:,}')
        w(f'  Unprocessed     : {unprocessed:,}')

        answered = CDR.objects.filter(answer_time__isnull=False).count()
        w(f'  Answered        : {answered:,}')

        # ── Revenue breakdown ─────────────────────────────────────────────────
        w(f'\n=== Revenue ===')
        from decimal import Decimal
        rev   = CDR.objects.aggregate(s=Sum('sell_revenue'))['s'] or 0
        cost  = CDR.objects.aggregate(s=Sum('buy_cost'))['s'] or 0
        billed= CDR.objects.aggregate(s=Sum('sell_billed_duration_sec'))['s'] or 0
        w(f'  Total sell revenue : {rev:.4f}')
        w(f'  Total buy cost     : {cost:.4f}')
        w(f'  Billed minutes     : {billed/60:.1f}')

        # ── Rate match breakdown ──────────────────────────────────────────────
        w(f'\n=== Rate Match ===')
        with_rate    = CDR.objects.filter(sell_revenue__gt=0).count()
        no_rate      = CDR.objects.filter(is_processed=True, sell_revenue=0,
                                          answer_time__isnull=False).count()
        no_dest      = CDR.objects.filter(is_processed=True, destination__isnull=True).count()
        w(f'  Answered with revenue  : {with_rate:,}')
        w(f'  Answered with no rate  : {no_rate:,}')
        w(f'  No destination matched : {no_dest:,}')

        # ── Sample of unrated answered CDRs ───────────────────────────────────
        samples = CDR.objects.filter(
            is_processed=True, sell_revenue=0, answer_time__isnull=False
        ).values('dnis', 'customer__name', 'destination__name')[:10]
        if samples:
            w(f'\n=== Sample unrated answered CDRs ===')
            for s in samples:
                w(f'  DNIS={s["dnis"]:<20} customer={s["customer__name"]}  '
                  f'dest={s["destination__name"]}')
