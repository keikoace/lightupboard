"""
Rate management: supplier tariffs, customer tariffs, rates per destination.
"""
from django.db import models
from apps.core.models import Company, Destination


class Tariff(models.Model):
    """A tariff plan belonging to a company (buy or sell side)."""
    SIDE_BUY = 'buy'
    SIDE_SELL = 'sell'
    SIDE_CHOICES = [(SIDE_BUY, 'Buy (Supplier)'), (SIDE_SELL, 'Sell (Customer)')]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='tariffs')
    name = models.CharField(max_length=200)
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    currency = models.CharField(max_length=3, default='USD')
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Default billing increment applied to new rates added to this tariff.
    # Individual rates may override these values.
    # Format: minimum/increment (e.g. 60/6 = 60-second minimum, 6-second steps).
    # Both default to 1 (per-second billing).
    default_billing_minimum = models.PositiveSmallIntegerField(
        default=1,
        help_text='Default minimum billed seconds for new rates (e.g. 60 for 60/x billing).',
    )
    default_billing_increment = models.PositiveSmallIntegerField(
        default=1,
        help_text='Default billing increment in seconds for new rates (e.g. 6 for x/6 billing).',
    )

    class Meta:
        ordering = ['-effective_date']

    def __str__(self):
        return f'{self.company} - {self.name} ({self.get_side_display()})'

    @property
    def billing_increment_display(self):
        return f'{self.default_billing_minimum}/{self.default_billing_increment}'

    def increment_warning(self):
        """
        For sell tariffs: return True if this tariff's default increment is less
        favourable than any active buy tariff (i.e. we would bill fewer seconds
        than the supplier can charge us on short calls).
        """
        if self.side != self.SIDE_SELL:
            return False
        buy_tariffs = Tariff.objects.filter(side=self.SIDE_BUY, is_active=True)
        for bt in buy_tariffs:
            if (self.default_billing_minimum < bt.default_billing_minimum or
                    self.default_billing_increment < bt.default_billing_increment):
                return True
        return False


class OriginGroup(models.Model):
    """
    A named group of ANI (caller) prefixes used for origin-based billing.
    e.g. "AT-A" covers calls originating from Austrian number prefix 1417.
    When a CDR's ANI matches a group's dialcodes, any Rate linked to this
    group takes precedence over the standard rate for the same destination.
    """
    name = models.CharField(max_length=100, unique=True,
                            help_text='Group code from vendor, e.g. AT-A')
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class OriginDialcode(models.Model):
    """An ANI prefix belonging to an origin group."""
    group = models.ForeignKey(OriginGroup, on_delete=models.CASCADE, related_name='dialcodes')
    prefix = models.CharField(max_length=30, help_text='ANI prefix, e.g. 1417')
    effective_date = models.DateField()

    class Meta:
        unique_together = ('group', 'prefix')
        ordering = ['prefix']

    def __str__(self):
        return f'{self.prefix} ({self.group.name})'


class Rate(models.Model):
    """A single rate entry within a tariff."""
    tariff = models.ForeignKey(Tariff, on_delete=models.CASCADE, related_name='rates')
    destination = models.ForeignKey(Destination, on_delete=models.PROTECT)
    prefix = models.CharField(max_length=30)
    rate_per_minute = models.DecimalField(max_digits=10, decimal_places=6)
    origin_group = models.ForeignKey(
        OriginGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='rates',
        help_text='If set, rate applies only when ANI matches this origin group. '
                  'Origin rates take priority over standard rates for the same destination.',
    )
    # Billing increment: minimum_duration_sec / billing_increment_sec
    # e.g. 60/6 = 60-second minimum, then 6-second steps.
    # Defaults to 1/1 (per-second). Both must be >= 1.
    minimum_duration_sec = models.PositiveSmallIntegerField(
        default=1,
        help_text='Minimum billed seconds (e.g. 60 for 60/x billing).',
    )
    billing_increment_sec = models.PositiveSmallIntegerField(
        default=1,
        help_text='Billing step in seconds after the minimum (e.g. 6 for x/6 billing).',
    )
    effective_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['prefix']
        unique_together = ('tariff', 'prefix', 'effective_date', 'origin_group')

    @property
    def billing_increment_display(self):
        return f'{self.minimum_duration_sec}/{self.billing_increment_sec}'

    def __str__(self):
        return f'{self.prefix} @ {self.rate_per_minute} ({self.billing_increment_display})'


class CostBase(models.Model):
    """Blended cost base for a destination (used in margin analysis)."""
    destination = models.ForeignKey(Destination, on_delete=models.CASCADE)
    period_start = models.DateField()
    period_end = models.DateField()
    blended_cost = models.DecimalField(max_digits=10, decimal_places=6)
    minutes = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-period_start']

    def __str__(self):
        return f'{self.destination} - {self.period_start}'


class AuditLog(models.Model):
    """Records every create/update/delete on Rate and Tariff."""
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Created'),
        (ACTION_UPDATE, 'Updated'),
        (ACTION_DELETE, 'Deleted'),
    ]

    object_type  = models.CharField(max_length=20)        # 'Rate' or 'Tariff'
    object_id    = models.PositiveIntegerField()
    object_repr  = models.CharField(max_length=300)       # str(instance) snapshot
    action       = models.CharField(max_length=10, choices=ACTION_CHOICES)
    user         = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL
    )
    timestamp    = models.DateTimeField(auto_now_add=True)
    before_json  = models.TextField(blank=True)           # JSON snapshot before change
    after_json   = models.TextField(blank=True)           # JSON snapshot after change

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.timestamp:%Y-%m-%d %H:%M} {self.action} {self.object_type} #{self.object_id}'
