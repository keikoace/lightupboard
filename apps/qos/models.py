"""
QoS / Traffic analysis: Call Detail Records and aggregated minute summaries.
"""
from django.db import models
from apps.core.models import Company, Switch, Destination


class CDR(models.Model):
    """Raw Call Detail Record."""
    call_id = models.CharField(max_length=100, db_index=True)
    switch = models.ForeignKey(Switch, null=True, blank=True, on_delete=models.SET_NULL)
    customer = models.ForeignKey(
        Company, on_delete=models.SET_NULL, null=True, related_name='cdr_as_customer'
    )
    supplier = models.ForeignKey(
        Company, on_delete=models.SET_NULL, null=True, related_name='cdr_as_supplier'
    )
    destination = models.ForeignKey(Destination, null=True, blank=True, on_delete=models.SET_NULL)
    ani = models.CharField(max_length=30, blank=True)   # Caller ID
    dnis = models.CharField(max_length=30, blank=True)  # Dialled number
    start_time = models.DateTimeField(db_index=True)
    answer_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_sec        = models.PositiveIntegerField(default=0)  # actual session duration
    switch_billed_sec   = models.PositiveIntegerField(default=0)  # pre-billed by switch (CSV "Billed Duration")
    # Split billed duration: buy-side and sell-side may use different increments.
    buy_billed_duration_sec = models.PositiveIntegerField(default=0)
    sell_billed_duration_sec = models.PositiveIntegerField(default=0)
    buy_rate = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    sell_rate = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    buy_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    sell_revenue = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    disconnect_cause = models.PositiveSmallIntegerField(null=True, blank=True)
    is_processed = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['start_time', 'customer']),
            models.Index(fields=['start_time', 'supplier']),
        ]

    def __str__(self):
        return f'{self.call_id} ({self.start_time:%Y-%m-%d %H:%M})'

    @property
    def gross_profit(self):
        return self.sell_revenue - self.buy_cost


class MinuteSummary(models.Model):
    """Hourly aggregated minutes/revenue — pre-computed for dashboards."""
    hour = models.DateTimeField(db_index=True)
    switch = models.ForeignKey(Switch, null=True, blank=True, on_delete=models.SET_NULL)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL)
    destination = models.ForeignKey(Destination, null=True, blank=True, on_delete=models.SET_NULL)
    side = models.CharField(max_length=8, choices=[('customer', 'Customer'), ('supplier', 'Supplier')])
    total_calls = models.PositiveIntegerField(default=0)
    connected_calls = models.PositiveIntegerField(default=0)
    total_minutes = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cost = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    asr = models.DecimalField(max_digits=5, decimal_places=2, default=0)   # Answer Seizure Ratio %
    acd = models.DecimalField(max_digits=8, decimal_places=2, default=0)   # Average Call Duration sec

    class Meta:
        ordering = ['-hour']
        unique_together = ('hour', 'switch', 'company', 'destination', 'side')
