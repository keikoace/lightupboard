"""
Email-based rate import: vendor rules and import history.
"""
from django.db import models
from apps.rates.models import Tariff


class VendorEmailRule(models.Model):
    """
    Maps a vendor's sender email to a tariff.
    When an email from sender_email arrives in the configured IMAP folder,
    matching the optional filters, the Excel attachment is imported into tariff.
    """
    name = models.CharField(max_length=200, help_text='Friendly label, e.g. "3U Telecom rates"')
    sender_email = models.EmailField(
        help_text='Exact sender address to match, e.g. rates@3utelecom.de'
    )
    tariff = models.ForeignKey(
        Tariff, on_delete=models.PROTECT, related_name='email_rules',
        help_text='Tariff to import rates into',
    )
    imap_folder = models.CharField(
        max_length=200, default='INBOX',
        help_text='IMAP folder to monitor, e.g. "INBOX" or "Rate Imports"',
    )
    subject_keyword = models.CharField(
        max_length=200, blank=True,
        help_text='Optional: only process emails whose subject contains this text (case-insensitive)',
    )
    attachment_pattern = models.CharField(
        max_length=200, blank=True,
        help_text='Optional: only process attachments whose filename contains this text (case-insensitive)',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.sender_email})'


class RateImportLog(models.Model):
    """Record of each email-triggered import attempt."""
    STATUS_SUCCESS = 'success'
    STATUS_ERROR   = 'error'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_ERROR,   'Error'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    rule            = models.ForeignKey(
        VendorEmailRule, on_delete=models.SET_NULL, null=True, related_name='logs'
    )
    email_from      = models.CharField(max_length=300)
    email_subject   = models.CharField(max_length=500, blank=True)
    attachment_name = models.CharField(max_length=300, blank=True)
    processed_at    = models.DateTimeField(auto_now_add=True)
    status          = models.CharField(max_length=10, choices=STATUS_CHOICES)
    error_message   = models.TextField(blank=True)

    # Stats from the import (JSON blob)
    destinations_created  = models.PositiveIntegerField(default=0)
    std_rates_created     = models.PositiveIntegerField(default=0)
    std_rates_updated     = models.PositiveIntegerField(default=0)
    origin_groups_created = models.PositiveIntegerField(default=0)
    origin_rates_created  = models.PositiveIntegerField(default=0)
    origin_rates_updated  = models.PositiveIntegerField(default=0)
    skipped               = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-processed_at']

    def __str__(self):
        return f'{self.processed_at:%Y-%m-%d %H:%M} — {self.rule} — {self.status}'
