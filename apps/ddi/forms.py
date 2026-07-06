from django import forms
from .models import DDIProfile, DDINumber, DDIRoute


class DDIProfileForm(forms.ModelForm):
    class Meta:
        model = DDIProfile
        fields = ['name', 'company', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class DDINumberForm(forms.ModelForm):
    class Meta:
        model = DDINumber
        fields = [
            'number', 'country', 'vendor', 'customer', 'destination',
            'buy_rate', 'sell_rate', 'is_active', 'ported_in', 'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'buy_rate': forms.NumberInput(attrs={'step': '0.000001'}),
            'sell_rate': forms.NumberInput(attrs={'step': '0.000001'}),
        }


class DDIRouteForm(forms.ModelForm):
    class Meta:
        model = DDIRoute
        fields = ['profile', 'supplier', 'priority', 'weight', 'is_active']
