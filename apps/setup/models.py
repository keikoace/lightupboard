"""
Setup-specific models — currently just Tickets.
"""
from django.db import models
from django.contrib.auth.models import User
from apps.core.models import Company


class Ticket(models.Model):
    PRIORITY_LOW      = 'low'
    PRIORITY_MEDIUM   = 'medium'
    PRIORITY_HIGH     = 'high'
    PRIORITY_CRITICAL = 'critical'
    PRIORITY_CHOICES  = [
        (PRIORITY_LOW,      'Low'),
        (PRIORITY_MEDIUM,   'Medium'),
        (PRIORITY_HIGH,     'High'),
        (PRIORITY_CRITICAL, 'Critical'),
    ]

    STATUS_OPEN    = 'open'
    STATUS_PENDING = 'pending'
    STATUS_CLOSED  = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN,    'Open'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_CLOSED,  'Closed'),
    ]

    subject     = models.CharField(max_length=300)
    company     = models.ForeignKey(
        Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets'
    )
    priority    = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    description = models.TextField(blank=True)
    created_by  = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_created'
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.subject}'

    @property
    def priority_badge_class(self):
        return {
            self.PRIORITY_LOW:      'bg-secondary',
            self.PRIORITY_MEDIUM:   'bg-info text-dark',
            self.PRIORITY_HIGH:     'bg-warning text-dark',
            self.PRIORITY_CRITICAL: 'bg-danger',
        }.get(self.priority, 'bg-secondary')

    @property
    def status_badge_class(self):
        return {
            self.STATUS_OPEN:    'bg-success',
            self.STATUS_PENDING: 'bg-warning text-dark',
            self.STATUS_CLOSED:  'bg-secondary',
        }.get(self.status, 'bg-secondary')
