from django import forms
from .models import VendorEmailRule


class VendorEmailRuleForm(forms.ModelForm):
    class Meta:
        model = VendorEmailRule
        fields = [
            'name', 'sender_email', 'tariff', 'imap_folder',
            'subject_keyword', 'attachment_pattern', 'is_active',
        ]
        widgets = {
            'name':               forms.TextInput(),
            'sender_email':       forms.EmailInput(),
            'imap_folder':        forms.TextInput(),
            'subject_keyword':    forms.TextInput(),
            'attachment_pattern': forms.TextInput(),
        }
        help_texts = {
            'imap_folder':        'Use "INBOX" or the name of a sub-folder, e.g. "Rate Imports".',
            'subject_keyword':    'Leave blank to match any subject.',
            'attachment_pattern': 'Leave blank to accept any Excel attachment.',
        }
