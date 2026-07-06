"""
Creates (or updates) the four Lightup billing profiles.

Usage:
    py manage.py seed_billing_profiles
"""
from django.core.management.base import BaseCommand
from apps.finance.models import BillingProfile


PROFILES = [
    {
        'name':        'Lightup Switzerland (USD)',
        'short_code':  'LNS-CH-USD',
        'currency':    'USD',
        'company_name':'Lightup Network Solutions GmbH & Co. KG',
        'address_line1': 'Hinterbergstr. 24',
        'address_line2': '6312 Steinhausen',
        'country':     'Schweiz',
        'phone':       '+49 (0)69 962 4456 0',
        'fax':         '+49 (0)69 962 4456 20',
        'email':       'info@lightupnet.de',
        'website':     'http://www.lightupnet.de',
        'ceo':         'Markus Stalder',
        'vat_id':      'CHE-371.769.877',
        'chamber':     'Handelsregister Zug',
        'iban':        'LT473250063188435974',
        'bic':         'REVOLT21',
        'bank_name':   'Revolut Bank UAB',
        'vat_rate':    '8.10',
        'next_invoice_number': 303700,  # set to current ISPcontrol sequence + buffer
    },
    {
        'name':        'Lightup Switzerland (CHF)',
        'short_code':  'LNS-CH-CHF',
        'currency':    'CHF',
        'company_name':'Lightup Network Solutions GmbH & Co. KG',
        'address_line1': 'Hinterbergstr. 24',
        'address_line2': '6312 Steinhausen',
        'country':     'Schweiz',
        'phone':       '+49 (0)69 962 4456 0',
        'fax':         '+49 (0)69 962 4456 20',
        'email':       'info@lightupnet.de',
        'website':     'http://www.lightupnet.de',
        'ceo':         'Markus Stalder',
        'vat_id':      'CHE-371.769.877',
        'chamber':     'Handelsregister Zug',
        'iban':        'LT473250063188435974',
        'bic':         'REVOLT21',
        'bank_name':   'Revolut Bank UAB',
        'vat_rate':    '8.10',
        'next_invoice_number': 303700,
    },
    {
        'name':        'Lightup Switzerland (EUR)',
        'short_code':  'LNS-CH-EUR',
        'currency':    'EUR',
        'company_name':'Lightup Network Solutions GmbH & Co. KG',
        'address_line1': 'Hinterbergstr. 24',
        'address_line2': '6312 Steinhausen',
        'country':     'Schweiz',
        'phone':       '+49 (0)69 962 4456 0',
        'fax':         '+49 (0)69 962 4456 20',
        'email':       'info@lightupnet.de',
        'website':     'http://www.lightupnet.de',
        'ceo':         'Markus Stalder',
        'vat_id':      'CHE-371.769.877',
        'chamber':     'Handelsregister Zug',
        'iban':        'LT473250063188435974',
        'bic':         'REVOLT21',
        'bank_name':   'Revolut Bank UAB',
        'vat_rate':    '8.10',
        'next_invoice_number': 303700,
    },
    {
        'name':        'Lightup Germany (EUR)',
        'short_code':  'LNS-DE-EUR',
        'currency':    'EUR',
        'company_name':'Lightup Network Solutions GmbH & Co. KG',
        'address_line1': 'Hinterbergstr. 24',
        'address_line2': '6312 Steinhausen',
        'country':     'Deutschland',
        'phone':       '+49 (0)69 962 4456 0',
        'fax':         '+49 (0)69 962 4456 20',
        'email':       'info@lightupnet.de',
        'website':     'http://www.lightupnet.de',
        'ceo':         'Markus Stalder',
        'vat_id':      '',   # fill in German VAT ID
        'chamber':     '',   # fill in German chamber
        'iban':        'LT473250063188435974',
        'bic':         'REVOLT21',
        'bank_name':   'Revolut Bank UAB',
        'vat_rate':    '19.00',
        'next_invoice_number': 303700,
    },
]


class Command(BaseCommand):
    help = 'Seed the four Lightup billing profiles'

    def handle(self, *args, **options):
        for data in PROFILES:
            profile, created = BillingProfile.objects.get_or_create(
                short_code=data['short_code'],
                defaults=data,
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Created: {profile.name}'))
            else:
                self.stdout.write(f'  Already exists: {profile.name} (skipped)')

        self.stdout.write(self.style.SUCCESS('\nDone. Edit next_invoice_number in Django admin to match ISPcontrol.'))
