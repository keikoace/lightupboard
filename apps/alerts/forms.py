from django import forms
from .models import AlertRule


class AlertRuleForm(forms.ModelForm):
    class Meta:
        model = AlertRule
        fields = [
            'name', 'alert_type', 'company', 'destination',
            'threshold_value', 'check_window_minutes',
            'email_recipients', 'is_active',
        ]
        widgets = {
            'email_recipients': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'ops@example.com, alerts@example.com',
            }),
            'threshold_value': forms.NumberInput(attrs={'step': '0.01'}),
        }
