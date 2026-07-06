"""
Finance: invoices, payments, credits, bill verification, term deals.
"""
from django.db import models
from apps.core.models import Company


class ExchangeRate(models.Model):
    """
    Daily exchange rate with EUR as base currency (sourced from ECB).
    To convert between non-EUR pairs, go via EUR:
      USD→CHF = (1/USD_rate) * CHF_rate
    """
    CURRENCIES = [('USD', 'US Dollar'), ('CHF', 'Swiss Franc'), ('EUR', 'Euro')]
    SOURCE_ECB = 'ECB'

    date          = models.DateField(db_index=True)
    base_currency = models.CharField(max_length=3, default='EUR')
    currency      = models.CharField(max_length=3, choices=CURRENCIES)
    rate          = models.DecimalField(max_digits=12, decimal_places=6,
                                        help_text='Units of currency per 1 EUR')
    source        = models.CharField(max_length=50, default=SOURCE_ECB)
    fetched_at    = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('date', 'base_currency', 'currency')]
        ordering = ['-date', 'currency']

    def __str__(self):
        return f'{self.date} EUR/{self.currency} = {self.rate}'


class BillingProfile(models.Model):
    """
    One of the four Lightup legal entities used as invoice sender.
    e.g. Lightup Switzerland (USD), Lightup Germany (EUR).
    """
    name        = models.CharField(max_length=100, help_text='Display name, e.g. "Lightup Switzerland (USD)"')
    short_code  = models.CharField(max_length=20, unique=True, help_text='e.g. LNS-CH-USD')
    currency    = models.CharField(max_length=3, default='USD')

    # Letterhead — sender block
    company_name  = models.CharField(max_length=200, default='Lightup Network Solutions GmbH & Co. KG')
    address_line1 = models.CharField(max_length=200, default='Hinterbergstr. 24')
    address_line2 = models.CharField(max_length=200, default='6312 Steinhausen')
    country       = models.CharField(max_length=100, default='Schweiz')
    phone         = models.CharField(max_length=50, blank=True, default='+49 (0)69 962 4456 0')
    fax           = models.CharField(max_length=50, blank=True, default='+49 (0)69 962 4456 20')
    email         = models.EmailField(blank=True, default='info@lightupnet.de')
    website       = models.CharField(max_length=200, blank=True, default='http://www.lightupnet.de')
    ceo           = models.CharField(max_length=100, blank=True, default='Markus Stalder')
    vat_id        = models.CharField(max_length=50, blank=True, help_text='e.g. CHE-371.769.877 or DE123456789')
    chamber       = models.CharField(max_length=100, blank=True, help_text='e.g. Handelsregister Zug')
    iban          = models.CharField(max_length=50, blank=True)
    bic           = models.CharField(max_length=20, blank=True)
    bank_name     = models.CharField(max_length=100, blank=True)

    # VAT
    vat_rate      = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                        help_text='Default VAT rate %, e.g. 8.10 or 19.00. 0 = VAT-exempt invoices.')

    # Invoice number sequence (shared across all invoices for this profile)
    next_invoice_number = models.PositiveIntegerField(default=1,
                          help_text='Next invoice number to assign — set to current ISPcontrol sequence when migrating.')

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def allocate_invoice_number(self):
        """Atomically grab the next invoice number and advance the counter."""
        from django.db import transaction
        with transaction.atomic():
            profile = BillingProfile.objects.select_for_update().get(pk=self.pk)
            num = profile.next_invoice_number
            profile.next_invoice_number = num + 1
            profile.save(update_fields=['next_invoice_number'])
        return num


class Invoice(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_SENT = 'sent'
    STATUS_PAID = 'paid'
    STATUS_OVERDUE = 'overdue'
    STATUS_VOID = 'void'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SENT, 'Sent'),
        (STATUS_PAID, 'Paid'),
        (STATUS_OVERDUE, 'Overdue'),
        (STATUS_VOID, 'Void'),
    ]

    TYPE_SALES = 'sales'
    TYPE_PURCHASE = 'purchase'
    TYPE_CHOICES = [(TYPE_SALES, 'Sales Invoice'), (TYPE_PURCHASE, 'Purchase Invoice')]

    company         = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='invoices')
    billing_profile = models.ForeignKey(
        BillingProfile, null=True, blank=True, on_delete=models.PROTECT, related_name='invoices',
        help_text='Lightup legal entity that appears as sender on this invoice',
    )
    invoice_type   = models.CharField(max_length=10, choices=TYPE_CHOICES)
    invoice_number = models.CharField(max_length=50, unique=True)
    status         = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    currency       = models.CharField(max_length=3, default='USD')
    period_start   = models.DateField()
    period_end     = models.DateField()
    issue_date     = models.DateField()
    due_date       = models.DateField()
    vat_rate       = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                         help_text='VAT rate applied on this invoice, e.g. 8.10')
    subtotal       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount     = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount   = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_paid    = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sent_at        = models.DateTimeField(null=True, blank=True)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date', '-invoice_number']

    def __str__(self):
        return f'{self.invoice_number} – {self.company}'

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid


class InvoiceLine(models.Model):
    invoice     = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    sort_order  = models.PositiveSmallIntegerField(default=0, help_text='Display order within invoice')
    quantity    = models.PositiveIntegerField(default=1)
    title       = models.CharField(max_length=200, default='Call Termination',
                                   help_text='Bold line title, e.g. "Call Termination"')
    description = models.TextField(blank=True,
                                   help_text='Detail text shown beneath title (mins × rate breakdown)')
    period_start = models.DateField(null=True, blank=True)
    period_end   = models.DateField(null=True, blank=True)
    minutes      = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    rate         = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    amount       = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return f'{self.invoice.invoice_number} – {self.title}'


class Payment(models.Model):
    METHOD_WIRE = 'wire'
    METHOD_CARD = 'card'
    METHOD_ACH = 'ach'
    METHOD_OTHER = 'other'
    METHOD_CHOICES = [
        (METHOD_WIRE, 'Wire Transfer'),
        (METHOD_CARD, 'Credit Card'),
        (METHOD_ACH, 'ACH'),
        (METHOD_OTHER, 'Other'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='payments')
    invoice = models.ForeignKey(
        Invoice, null=True, blank=True, on_delete=models.SET_NULL, related_name='payments'
    )
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=METHOD_WIRE)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f'{self.company} – {self.amount} {self.currency} ({self.payment_date})'


class TermDeal(models.Model):
    """Volume / term commitment deal between carrier and us."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='term_deals')
    destination_name = models.CharField(max_length=200)
    committed_minutes = models.DecimalField(max_digits=14, decimal_places=2)
    rate = models.DecimalField(max_digits=10, decimal_places=6)
    currency = models.CharField(max_length=3, default='USD')
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.company} – {self.destination_name} ({self.start_date} to {self.end_date})'


class BillVerification(models.Model):
    """Cross-check between supplier bill and our CDR-calculated cost."""
    STATUS_PENDING = 'pending'
    STATUS_OK = 'ok'
    STATUS_DISPUTE = 'dispute'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_OK, 'Agreed'),
        (STATUS_DISPUTE, 'Disputed'),
    ]

    supplier = models.ForeignKey(Company, on_delete=models.CASCADE)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL)
    period_start = models.DateField()
    period_end = models.DateField()
    supplier_amount = models.DecimalField(max_digits=14, decimal_places=2)
    our_amount = models.DecimalField(max_digits=14, decimal_places=2)
    variance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_start']

    def __str__(self):
        return f'{self.supplier} – {self.period_start} (variance: {self.variance})'


class RevenueShare(models.Model):
    """
    Revenue share agreement between Lightup and a partner company.
    E.g. partner earns X% of margin on traffic they refer or co-own.
    """
    company     = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='revenue_shares',
                                    help_text='The partner company receiving the revenue share')
    description = models.CharField(max_length=300, blank=True,
                                   help_text='What this share covers (e.g. "Switzerland termination margin")')
    share_pct   = models.DecimalField(max_digits=6, decimal_places=3,
                                      help_text='Percentage of revenue/margin to share, e.g. 25.000')
    start_date  = models.DateField(null=True, blank=True)
    end_date    = models.DateField(null=True, blank=True, help_text='Leave blank for open-ended')
    is_active   = models.BooleanField(default=True)
    notes       = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_active', 'company__name']

    def __str__(self):
        return f'{self.company} – {self.share_pct}%'


class BillableItem(models.Model):
    """Per-customer shopping cart item — recurring or one-time billable line."""

    BILLING_ONE_TIME    = 'one_time'
    BILLING_MONTHLY     = 'monthly'
    BILLING_QUARTERLY   = 'quarterly'
    BILLING_HALF_YEARLY = 'half_yearly'
    BILLING_YEARLY      = 'yearly'
    BILLING_TYPE_CHOICES = [
        (BILLING_ONE_TIME,    'One-time'),
        (BILLING_MONTHLY,     'Monthly'),
        (BILLING_QUARTERLY,   'Quarterly (3-monthly)'),
        (BILLING_HALF_YEARLY, 'Half-yearly (6-monthly)'),
        (BILLING_YEARLY,      'Yearly'),
    ]

    customer          = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='billable_items')
    description       = models.CharField(max_length=500, help_text='Item name as it appears on the invoice')
    billing_type      = models.CharField(max_length=15, choices=BILLING_TYPE_CHOICES, default=BILLING_MONTHLY)
    unit_price        = models.DecimalField(max_digits=14, decimal_places=4)
    quantity          = models.DecimalField(max_digits=10, decimal_places=4, default=1)
    currency          = models.CharField(max_length=3, default='USD')
    is_active         = models.BooleanField(default=True)
    service_start     = models.DateField(null=True, blank=True, help_text='Date service began')
    next_billing_date = models.DateField(null=True, blank=True, help_text='Next auto-invoice date (recurring only)')
    notes             = models.TextField(blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_active', 'description']

    def __str__(self):
        return f'{self.customer} – {self.description}'

    @property
    def total(self):
        return self.unit_price * self.quantity

    @property
    def is_recurring(self):
        return self.billing_type != self.BILLING_ONE_TIME
