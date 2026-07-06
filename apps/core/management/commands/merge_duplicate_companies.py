"""
Merge the 7 known duplicate Company pairs.

In each pair the LOWER id is kept (original SQLite data).
The HIGHER id (from carrier import) is merged into it then deleted.

Re-points all FK/M2M references:
  CDR.customer / CDR.supplier
  MinuteSummary.company
  DDINumber.customer / DDINumber.vendor (if exists)
  Tariff.company
  Invoice.company
  BillableItem.company
  Trunk.company
  AlertEvent references
  account_managers / portal_users (M2M through auth)

Usage:
    python manage.py merge_duplicate_companies [--dry-run]
"""
from django.core.management.base import BaseCommand
from django.db import transaction

# (keep_id, merge_id)  — keep is lower, merge is the import duplicate
PAIRS = [
    (39,  2),    # 3U Telecom  — NOTE: keep ID 2 (supplier) ... actually both are "3U Telecom"
    (54,  5),    # Bitcall
    (57, 211),   # Brilliant Telecom Limited
    (69, 213),   # Cloud IT Services GmbH
    (92, 216),   # Haloma Invest Ltd
    (153, 217),  # Smarted Ltd
    (203, 218),  # YIPL GmbH
]

# For 3U Telecom: ID 2 is the original supplier, ID 39 was created by import.
# The import row has role=both, the original has role=supplier.
# We want to KEEP ID 2 (original) and merge ID 39 into it.
# Fix the pair so lower numerical id isn't always "keep":
PAIRS[0] = (2, 39)   # keep ID 2, merge ID 39 for 3U Telecom


def _merge_role(keep, merge):
    """Promote role if the duplicate adds customer or supplier coverage."""
    both = {'both'}
    if keep.role == 'both' or merge.role == 'both':
        return 'both'
    if keep.role != merge.role:
        return 'both'
    return keep.role


class Command(BaseCommand):
    help = 'Merge 7 known duplicate Company records'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        from apps.core.models import Company, Trunk
        from apps.qos.models import CDR, MinuteSummary
        from apps.rates.models import Tariff

        # Optional models — import safely
        try:
            from apps.ddi.models import DDINumber
        except ImportError:
            DDINumber = None
        try:
            from apps.finance.models import Invoice, BillableItem
        except ImportError:
            Invoice = BillableItem = None
        try:
            from apps.alerts.models import AlertEvent
        except ImportError:
            AlertEvent = None
        try:
            from apps.setup.models import InterconnectAgreement
        except ImportError:
            InterconnectAgreement = None

        with transaction.atomic():
            for keep_id, merge_id in PAIRS:
                try:
                    keep  = Company.objects.get(pk=keep_id)
                    merge = Company.objects.get(pk=merge_id)
                except Company.DoesNotExist:
                    self.stdout.write(f'  SKIP  IDs {keep_id}/{merge_id} — one not found')
                    continue

                self.stdout.write(f'\nMerging "{merge.name}" (ID {merge_id}) → "{keep.name}" (ID {keep_id})')

                new_role = _merge_role(keep, merge)
                counts = {}

                if not dry_run:
                    # ── Core FKs ──────────────────────────────────────────────
                    n = CDR.objects.filter(customer=merge).update(customer=keep)
                    counts['CDR.customer'] = n
                    n = CDR.objects.filter(supplier=merge).update(supplier=keep)
                    counts['CDR.supplier'] = n

                    n = MinuteSummary.objects.filter(company=merge).update(company=keep)
                    counts['MinuteSummary'] = n

                    n = Tariff.objects.filter(company=merge).update(company=keep)
                    counts['Tariff'] = n

                    n = Trunk.objects.filter(company=merge).update(company=keep)
                    counts['Trunk'] = n

                    if DDINumber:
                        n = DDINumber.objects.filter(customer=merge).update(customer=keep)
                        counts['DDI.customer'] = n
                        n = DDINumber.objects.filter(vendor=merge).update(vendor=keep)
                        counts['DDI.vendor'] = n

                    if Invoice:
                        n = Invoice.objects.filter(company=merge).update(company=keep)
                        counts['Invoice'] = n
                    if BillableItem:
                        n = BillableItem.objects.filter(customer=merge).update(customer=keep)
                        counts['BillableItem'] = n

                    if AlertEvent:
                        for field in ('company', 'supplier', 'customer'):
                            if hasattr(AlertEvent, field):
                                n = AlertEvent.objects.filter(**{field: merge}).update(**{field: keep})
                                counts[f'Alert.{field}'] = n

                    if InterconnectAgreement:
                        for field in ('company_a', 'company_b'):
                            if hasattr(InterconnectAgreement, field):
                                n = InterconnectAgreement.objects.filter(
                                    **{field: merge}
                                ).update(**{field: keep})
                                counts[f'Interconnect.{field}'] = n

                    # ── M2M: account_managers + portal_users ──────────────────
                    for u in merge.account_managers.all():
                        keep.account_managers.add(u)
                    for u in merge.portal_users.all():
                        keep.portal_users.add(u)

                    # ── Promote role if needed ────────────────────────────────
                    if keep.role != new_role:
                        keep.role = new_role
                        self.stdout.write(f'  role promoted → {new_role}')

                    # ── Merge notes ───────────────────────────────────────────
                    if merge.notes and merge.notes not in keep.notes:
                        keep.notes = (keep.notes + '\n' + merge.notes).strip()

                    keep.save()
                    merge.delete()

                for k, v in counts.items():
                    if v:
                        self.stdout.write(f'  re-pointed {v:>4} {k}')
                self.stdout.write(self.style.SUCCESS(f'  ✓ done'))

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('\n[DRY RUN] — no changes written'))
            else:
                self.stdout.write(self.style.SUCCESS('\nAll duplicates merged.'))
