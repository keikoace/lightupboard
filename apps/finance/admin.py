from django.contrib import admin
from .models import BillingProfile, Invoice, InvoiceLine, Payment, BillableItem


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    fields = ['sort_order', 'quantity', 'title', 'description', 'period_start', 'period_end', 'minutes', 'amount']


@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
    list_display  = ['name', 'short_code', 'currency', 'vat_rate', 'next_invoice_number', 'is_active']
    list_editable = ['next_invoice_number']
    fieldsets = [
        ('Identity', {'fields': ['name', 'short_code', 'currency', 'is_active']}),
        ('Letterhead', {'fields': [
            'company_name', 'address_line1', 'address_line2', 'country',
            'phone', 'fax', 'email', 'website', 'ceo',
        ]}),
        ('Legal & Banking', {'fields': ['vat_id', 'chamber', 'iban', 'bic', 'bank_name']}),
        ('VAT & Numbering', {'fields': ['vat_rate', 'next_invoice_number']}),
    ]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ['invoice_number', 'company', 'billing_profile', 'currency',
                     'total_amount', 'status', 'issue_date']
    list_filter   = ['status', 'invoice_type', 'billing_profile', 'currency']
    search_fields = ['invoice_number', 'company__name']
    inlines       = [InvoiceLineInline]
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ['company', 'amount', 'currency', 'payment_date', 'method']
    list_filter   = ['method', 'currency']
    search_fields = ['company__name', 'reference']


@admin.register(BillableItem)
class BillableItemAdmin(admin.ModelAdmin):
    list_display  = ['customer', 'description', 'billing_type', 'unit_price', 'currency', 'is_active', 'next_billing_date']
    list_filter   = ['billing_type', 'is_active', 'currency']
    search_fields = ['customer__name', 'description']
