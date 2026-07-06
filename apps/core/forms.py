from django import forms
from django.contrib.auth.models import User
from .models import Company, Switch, Destination, DisconnectCause, Trunk


class CompanyForm(forms.ModelForm):
    account_managers = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('first_name', 'username'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Account Managers',
    )
    portal_users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('first_name', 'username'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Customer Portal Users',
        help_text="Users who can log in at /portal/ and view this company's invoices, traffic and DIDs.",
    )

    class Meta:
        model = Company
        fields = [
            'name', 'role', 'currency', 'country',
            'email', 'phone', 'address', 'credit_limit',
            'payment_terms', 'vat_exempt', 'customer_number',
            'account_managers', 'portal_users', 'is_active', 'notes',
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'role': forms.Select(),
            'credit_limit': forms.NumberInput(attrs={'step': '0.01'}),
        }


class SwitchForm(forms.ModelForm):
    class Meta:
        model = Switch
        fields = ['name', 'ip_address', 'description', 'is_active']
        widgets = {
            'description': forms.TextInput(),
        }


class DestinationForm(forms.ModelForm):
    class Meta:
        model = Destination
        fields = ['prefix', 'name', 'country', 'region', 'is_active']


class DisconnectCauseForm(forms.ModelForm):
    class Meta:
        model = DisconnectCause
        fields = ['code', 'name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class PortalUserForm(forms.Form):
    """Create or edit a portal user + link them to a company."""
    username   = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name  = forms.CharField(max_length=150, required=False)
    email      = forms.EmailField(required=False)
    password   = forms.CharField(
        widget=forms.PasswordInput,
        required=False,
        help_text='Leave blank to keep current password (edit mode).',
    )
    company = forms.ModelChoiceField(
        queryset=Company.objects.filter(is_active=True).order_by('name'),
        help_text='The company this user will have portal access to.',
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._edit_user = user
        if user:
            # Pre-fill in edit mode
            self.fields['username'].initial   = user.username
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial  = user.last_name
            self.fields['email'].initial      = user.email
            self.fields['password'].required  = False
        else:
            self.fields['password'].required  = True
            self.fields['password'].help_text = ''

    def clean_username(self):
        from django.contrib.auth.models import User
        uname = self.cleaned_data['username']
        qs = User.objects.filter(username=uname)
        if self._edit_user:
            qs = qs.exclude(pk=self._edit_user.pk)
        if qs.exists():
            raise forms.ValidationError('A user with that username already exists.')
        return uname


class TrunkForm(forms.ModelForm):
    class Meta:
        model = Trunk
        fields = ['name', 'abbreviation', 'prefix', 'direction', 'buy_tariff', 'sell_tariff', 'is_active', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
            'prefix': forms.TextInput(attrs={'placeholder': 'e.g. out1 or leave blank'}),
        }
        help_texts = {
            'prefix': 'Optional SIP/routing prefix that identifies this trunk on the switch.',
        }
