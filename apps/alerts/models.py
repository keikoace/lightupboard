"""
Alerts: traffic alerts, threshold triggers, unprocessed CDR tracking.
"""
from django.db import models
from apps.core.models import Company, Switch, Destination


class AlertRule(models.Model):
    """A threshold rule that triggers an alert when breached."""
    TYPE_TRAFFIC_DROP = 'traffic_drop'
    TYPE_TRAFFIC_SPIKE = 'traffic_spike'
    TYPE_ASR_LOW = 'asr_low'
    TYPE_UNPROCESSED = 'unprocessed'
    TYPE_CHOICES = [
        (TYPE_TRAFFIC_DROP, 'Traffic Drop'),
        (TYPE_TRAFFIC_SPIKE, 'Traffic Spike'),
        (TYPE_ASR_LOW, 'Low ASR'),
        (TYPE_UNPROCESSED, 'Unprocessed Traffic'),
    ]

    name = models.CharField(max_length=200)
    alert_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL)
    destination = models.ForeignKey(Destination, null=True, blank=True, on_delete=models.SET_NULL)
    threshold_value = models.DecimalField(max_digits=10, decimal_places=2)
    check_window_minutes = models.PositiveIntegerField(default=60)
    email_recipients = models.TextField(blank=True, help_text='Comma-separated email addresses')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} ({self.get_alert_type_display()})'


class AlertEvent(models.Model):
    """A fired alert instance."""
    STATUS_OPEN = 'open'
    STATUS_ACK = 'acknowledged'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_ACK, 'Acknowledged'),
        (STATUS_CLOSED, 'Closed'),
    ]

    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='events')
    fired_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_OPEN)
    details = models.TextField(blank=True)
    acknowledged_by = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ['-fired_at']

    def __str__(self):
        return f'{self.rule} @ {self.fired_at:%Y-%m-%d %H:%M}'
