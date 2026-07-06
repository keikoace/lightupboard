from django import forms
from .models import Tariff, Rate, CostBase


class TariffForm(forms.ModelForm):
    class Meta:
        model = Tariff
        fields = [
            'company', 'name', 'side', 'currency',
            'effective_date', 'expiry_date', 'is_active', 'notes',
            'default_billing_minimum', 'default_billing_increment',
        ]
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'default_billing_minimum': forms.NumberInput(
                attrs={'min': 1, 'placeholder': '60'}
            ),
            'default_billing_increment': forms.NumberInput(
                attrs={'min': 1, 'placeholder': '6'}
            ),
        }
        help_texts = {
            'default_billing_minimum': (
                'Minimum seconds charged per call (e.g. 60). '
                'New rates added to this tariff inherit this value.'
            ),
            'default_billing_increment': (
                'Seconds per billing step after the minimum (e.g. 6). '
                'Use 1 for per-second billing.'
            ),
        }


class RateForm(forms.ModelForm):
    class Meta:
        model = Rate
        fields = [
            'tariff', 'destination', 'prefix', 'rate_per_minute',
            'minimum_duration_sec', 'billing_increment_sec',
            'effective_date', 'expiry_date',
        ]
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'rate_per_minute': forms.NumberInput(attrs={'step': '0.000001'}),
            'minimum_duration_sec': forms.NumberInput(attrs={'min': 1, 'placeholder': '60'}),
            'billing_increment_sec': forms.NumberInput(attrs={'min': 1, 'placeholder': '6'}),
        }
        help_texts = {
            'minimum_duration_sec': 'Minimum billed seconds for this rate (e.g. 60).',
            'billing_increment_sec': 'Billing step in seconds after the minimum (e.g. 6).',
        }
