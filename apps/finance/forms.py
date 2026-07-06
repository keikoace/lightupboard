from django import forms
from .models import Invoice, InvoiceLine, Payment, TermDeal, BillVerification


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            'company', 'invoice_type', 'invoice_number', 'status',
            'currency', 'period_start', 'period_end',
            'issue_date', 'due_date',
            'subtotal', 'tax_amount', 'total_amount', 'notes',
        ]
        widgets = {
            'period_start': forms.DateInput(attrs={'type': 'date'}),
            'period_end': forms.DateInput(attrs={'type': 'date'}),
            'issue_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'subtotal': forms.NumberInput(attrs={'step': '0.01'}),
            'tax_amount': forms.NumberInput(attrs={'step': '0.01'}),
            'total_amount': forms.NumberInput(attrs={'step': '0.01'}),
        }


class InvoiceLineForm(forms.ModelForm):
    class Meta:
        model = InvoiceLine
        fields = ['description', 'minutes', 'rate', 'amount']
        widgets = {
            'rate': forms.NumberInput(attrs={'step': '0.000001'}),
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            'company', 'invoice', 'payment_date', 'amount',
            'currency', 'method', 'reference', 'notes',
        ]
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
        }


class TermDealForm(forms.ModelForm):
    class Meta:
        model = TermDeal
        fields = [
            'company', 'destination_name', 'committed_minutes',
            'rate', 'currency', 'start_date', 'end_date', 'is_active', 'notes',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'rate': forms.NumberInput(attrs={'step': '0.000001'}),
            'committed_minutes': forms.NumberInput(attrs={'step': '0.01'}),
        }


class BillVerificationForm(forms.ModelForm):
    class Meta:
        model = BillVerification
        fields = [
            'supplier', 'invoice', 'period_start', 'period_end',
            'supplier_amount', 'our_amount', 'variance', 'status', 'notes',
        ]
        widgets = {
            'period_start': forms.DateInput(attrs={'type': 'date'}),
            'period_end': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'supplier_amount': forms.NumberInput(attrs={'step': '0.01'}),
            'our_amount': forms.NumberInput(attrs={'step': '0.01'}),
            'variance': forms.NumberInput(attrs={'step': '0.01'}),
        }
