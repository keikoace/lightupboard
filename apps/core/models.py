"""
Core models shared across the platform.
Company is the central entity — it can be a customer, supplier, or both.
Switch represents an SBC (Session Border Controller).
"""
import uuid
from django.db import models
from django.contrib.auth.models import User


class Company(models.Model):
    ROLE_CUSTOMER = 'customer'
    ROLE_SUPPLIER = 'supplier'
    ROLE_BOTH = 'both'
    ROLE_CHOICES = [
        (ROLE_CUSTOMER, 'Customer'),
        (ROLE_SUPPLIER, 'Supplier'),
        (ROLE_BOTH, 'Customer & Supplier'),
    ]

    TERMS_NONE    = ''
    TERMS_PREPAY  = 'PrePay'
    TERMS_7_3     = '7/3'
    TERMS_7_7     = '7/7'
    TERMS_15_3    = '15/3'
    TERMS_15_5    = '15/5'
    TERMS_15_7    = '15/7'
    TERMS_7_15    = '7/15'
    TERMS_15_15   = '15/15'
    TERMS_30_7    = '30/7'
    TERMS_30_10   = '30/10'
    TERMS_30_15   = '30/15'
    TERMS_30_30   = '30/30'
    TERMS_30_60   = '30/60'
    PAYMENT_TERMS_CHOICES = [
        (TERMS_NONE,   '— None —'),
        (TERMS_PREPAY, 'PrePay'),
        (TERMS_7_3,    '7/3  (10 days)'),
        (TERMS_7_7,    '7/7  (14 days)'),
        (TERMS_15_3,   '15/3  (18 days)'),
        (TERMS_15_5,   '15/5  (20 days)'),
        (TERMS_15_7,   '15/7  (22 days)'),
        (TERMS_7_15,   '7/15  (22 days)'),
        (TERMS_15_15,  '15/15  (30 days)'),
        (TERMS_30_7,   '30/7  (37 days)'),
        (TERMS_30_10,  '30/10  (40 days)'),
        (TERMS_30_15,  '30/15  (45 days)'),
        (TERMS_30_30,  '30/30  (60 days)'),
        (TERMS_30_60,  '30/60  (90 days)'),
    ]
    # Maps payment term → total payment cycle days (for due-date calculation)
    TERMS_DAYS = {
        '': 0, 'PrePay': 0, '7/3': 10, '7/7': 14, '15/3': 18,
        '15/5': 20, '15/7': 22, '7/15': 22, '15/15': 30,
        '30/7': 37, '30/10': 40, '30/15': 45, '30/30': 60, '30/60': 90,
    }

    name            = models.CharField(max_length=200)
    customer_number = models.PositiveIntegerField(
        null=True, blank=True, unique=True,
        help_text='Sequential customer ID shown on invoices (e.g. 301753)',
    )
    role    = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_BOTH)
    address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    vat_exempt = models.BooleanField(
        default=False,
        help_text='If checked, VAT is set to 0% on all invoices for this company (e.g. foreign B2B carriers)',
    )
    account_managers = models.ManyToManyField(
        User,
        blank=True,
        related_name='managed_companies',
        help_text='Account managers responsible for this company',
    )
    portal_users = models.ManyToManyField(
        User,
        blank=True,
        related_name='customer_companies',
        help_text='Users who can log into the customer portal and view this company\'s data',
    )
    payment_terms = models.CharField(
        max_length=10, blank=True, default='',
        choices=PAYMENT_TERMS_CHOICES,
        help_text='Billing period / payment due days (e.g. 30/7 = invoice monthly, due in 7 days)',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Companies'
        ordering = ['name']

    def __str__(self):
        return self.name


class Trunk(models.Model):
    """
    A routing sub-entity under a Company.
    One Company may have many Trunks (e.g. out1, out2, olo, sc …).
    Billing is always aggregated at the Company level — Trunks are purely
    organisational / routing identifiers.
    """
    DIRECTION_IN   = 'inbound'
    DIRECTION_OUT  = 'outbound'
    DIRECTION_BOTH = 'both'
    DIRECTION_CHOICES = [
        (DIRECTION_IN,   'Inbound'),
        (DIRECTION_OUT,  'Outbound'),
        (DIRECTION_BOTH, 'Both'),
    ]

    company     = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='trunks')
    name        = models.CharField(max_length=200)
    abbreviation = models.CharField(max_length=50, blank=True)
    prefix      = models.CharField(
        max_length=50, blank=True,
        help_text='SIP/routing prefix used to identify this trunk on the switch. Leave blank if unused.',
    )
    direction   = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default=DIRECTION_BOTH)
    # Tariffs are referenced by string to avoid a circular import (rates → core).
    buy_tariff  = models.ForeignKey(
        'rates.Tariff', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='trunks_buying',
    )
    sell_tariff = models.ForeignKey(
        'rates.Tariff', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='trunks_selling',
    )
    is_active   = models.BooleanField(default=True)
    notes       = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['company', 'name']
        unique_together = ('company', 'name')

    def __str__(self):
        return f'{self.company.name} / {self.name}'


class Switch(models.Model):
    """Session Border Controller / media gateway."""
    name = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField()
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    api_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text='Secret token used by this switch to authenticate CDR API posts.',
    )

    class Meta:
        verbose_name_plural = 'Switches'
        ordering = ['name']

    def __str__(self):
        return self.name


class Destination(models.Model):
    """Dialling destination / zone."""
    name = models.CharField(max_length=200)
    prefix = models.CharField(max_length=30)
    country = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    invoice_group = models.CharField(
        max_length=100, blank=True,
        help_text='Invoice line label e.g. "Germany Fixed". Destinations sharing a group are merged into one invoice line.',
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.prefix} – {self.name}'


class DisconnectCause(models.Model):
    """SIP / Q.850 disconnect/release cause code."""
    code = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} – {self.name}'
