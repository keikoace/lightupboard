"""
check_alerts — Evaluate all active AlertRules and fire AlertEvents.

Rules evaluated:
  traffic_drop   — sell minutes in the last window < threshold % of prior window
  traffic_spike  — sell minutes in the last window > threshold % of prior window
  asr_low        — ASR in the last window < threshold %
  unprocessed    — count of unprocessed CDRs > threshold

Run on a cron / Windows Task Scheduler, e.g. every 15 minutes:
  py manage.py check_alerts

Each rule will not re-fire while an open event for it already exists,
preventing duplicate alert storms.
"""
from decimal import Decimal
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils.timezone import now
from django.db.models import Sum, Count

from apps.alerts.models import AlertRule, AlertEvent
from apps.qos.models import CDR, MinuteSummary


class Command(BaseCommand):
    help = 'Evaluate active alert rules and create AlertEvent records.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would fire without creating events or sending email.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no events will be created.\n'))

        rules = AlertRule.objects.filter(is_active=True).select_related('company', 'destination')
        self.stdout.write(f'Evaluating {rules.count()} active rules...\n')

        fired = 0
        for rule in rules:
            result = self._evaluate(rule)
            if result is None:
                continue  # not breached

            # Suppress if open event already exists for this rule
            if AlertEvent.objects.filter(rule=rule, status=AlertEvent.STATUS_OPEN).exists():
                self.stdout.write(f'  SUPPRESSED (open event exists): {rule.name}')
                continue

            self.stdout.write(self.style.WARNING(f'  FIRING: {rule.name} — {result}'))

            if not dry_run:
                event = AlertEvent.objects.create(
                    rule=rule,
                    status=AlertEvent.STATUS_OPEN,
                    details=result,
                )
                self._notify(rule, event, result)
            fired += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone — {fired} event(s) {"would be " if dry_run else ""}fired.'
        ))

    # ── Evaluators ────────────────────────────────────────────────────────────

    def _evaluate(self, rule):
        """Return a details string if the rule is breached, else None."""
        t = rule.alert_type
        window = timedelta(minutes=rule.check_window_minutes)
        cutoff = now() - window

        if t == AlertRule.TYPE_TRAFFIC_DROP:
            return self._check_traffic_change(rule, cutoff, window, drop=True)
        elif t == AlertRule.TYPE_TRAFFIC_SPIKE:
            return self._check_traffic_change(rule, cutoff, window, drop=False)
        elif t == AlertRule.TYPE_ASR_LOW:
            return self._check_asr(rule, cutoff)
        elif t == AlertRule.TYPE_UNPROCESSED:
            return self._check_unprocessed(rule)
        return None

    def _minute_summary_qs(self, rule, start, end):
        qs = MinuteSummary.objects.filter(
            hour__gte=start, hour__lt=end, side='customer'
        )
        if rule.company:
            qs = qs.filter(company=rule.company)
        if rule.destination:
            qs = qs.filter(destination=rule.destination)
        return qs

    def _check_traffic_change(self, rule, cutoff, window, drop):
        """
        Compare current window vs prior window.
        For traffic_drop: breach if current < prior * (1 - threshold/100)
        For traffic_spike: breach if current > prior * (1 + threshold/100)
        """
        prior_start = cutoff - window
        current_mins = (
            self._minute_summary_qs(rule, cutoff, now())
            .aggregate(t=Sum('total_minutes'))['t'] or Decimal('0')
        )
        prior_mins = (
            self._minute_summary_qs(rule, prior_start, cutoff)
            .aggregate(t=Sum('total_minutes'))['t'] or Decimal('0')
        )

        if prior_mins == 0:
            return None  # no baseline, can't evaluate

        pct_change = float((current_mins - prior_mins) / prior_mins * 100)
        threshold  = float(rule.threshold_value)

        if drop and pct_change < -threshold:
            return (
                f'Traffic dropped {abs(pct_change):.1f}% below prior window '
                f'(current {current_mins:.1f} min vs prior {prior_mins:.1f} min). '
                f'Threshold: -{threshold}%'
            )
        if not drop and pct_change > threshold:
            return (
                f'Traffic spiked {pct_change:.1f}% above prior window '
                f'(current {current_mins:.1f} min vs prior {prior_mins:.1f} min). '
                f'Threshold: +{threshold}%'
            )
        return None

    def _check_asr(self, rule, cutoff):
        """Breach if ASR in current window < threshold %."""
        qs = MinuteSummary.objects.filter(
            hour__gte=cutoff, side='customer'
        )
        if rule.company:
            qs = qs.filter(company=rule.company)
        if rule.destination:
            qs = qs.filter(destination=rule.destination)

        agg = qs.aggregate(calls=Sum('total_calls'), connected=Sum('connected_calls'))
        total = agg['calls'] or 0
        conn  = agg['connected'] or 0
        if total == 0:
            return None

        asr = conn / total * 100
        if asr < float(rule.threshold_value):
            return (
                f'ASR {asr:.1f}% is below threshold {rule.threshold_value}% '
                f'({conn}/{total} calls connected in the last {rule.check_window_minutes} min).'
            )
        return None

    def _check_unprocessed(self, rule):
        """Breach if unprocessed CDR count > threshold."""
        qs = CDR.objects.filter(is_processed=False)
        if rule.company:
            qs = qs.filter(customer=rule.company)
        count = qs.count()
        if count > int(rule.threshold_value):
            return (
                f'{count} unprocessed CDRs exceed threshold {int(rule.threshold_value)}.'
            )
        return None

    # ── Notification ──────────────────────────────────────────────────────────

    def _notify(self, rule, event, details):
        recipients = [e.strip() for e in rule.email_recipients.split(',') if e.strip()]
        if not recipients:
            return
        try:
            send_mail(
                subject=f'[Alert] {rule.name}',
                message=(
                    f'Alert rule "{rule.name}" fired at {event.fired_at:%Y-%m-%d %H:%M UTC}.\n\n'
                    f'{details}\n\n'
                    f'Log in to review: /alerts/traffic/'
                ),
                from_email=None,
                recipient_list=recipients,
                fail_silently=True,
            )
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'  Email failed: {exc}'))
