"""
Import companies scraped from Springboard ASA carrier list.
Deduplicates by master carrier name.
Run: py manage.py import_springboard_companies
"""
from django.core.management.base import BaseCommand
from apps.core.models import Company

COMPANIES = [
    # (name, role)
    # role: 'both' = supplier & customer, 'supplier' = buy only, 'customer' = sell only
    ('2way Telecom',                    'both'),
    ('3U Telecom',                      'both'),
    ('4 Carriers',                      'both'),
    ('Acepeak',                         'both'),
    ('ADC Telecom',                     'both'),
    ('Advancetel',                      'both'),
    ('Aiwo',                            'both'),
    ('Alfacall',                        'both'),
    ('Alizee Telecom',                  'both'),
    ('Alka IP',                         'both'),
    ('All Time Telecom',                'both'),
    ('Aovatalk',                        'both'),
    ('Asal',                            'both'),
    ('Australian Phone Company',        'both'),
    ('BBT Voice',                       'both'),
    ('Bharti Airtel',                   'both'),
    ('Bitcall',                         'both'),
    ('Biteh',                           'both'),
    ('Bridgevoice Inc',                 'both'),
    ('Brilliant Telecom Limited',       'both'),
    ('Callcom',                         'both'),
    ('Call Hub',                        'both'),
    ('Callsy Network LLC',              'both'),
    ('Capital City Service Limited',    'both'),
    ('Caprus Digital',                  'both'),
    ('CBC LLC',                         'both'),
    ('Chat Link',                       'both'),
    ('China Mobile',                    'both'),
    ('China Skyline',                   'customer'),
    ('Cima Telecom',                    'customer'),
    ('Circells',                        'customer'),
    ('Cloud IT Services GmbH',          'both'),
    ('CommPeak',                        'both'),
    ('Comnica',                         'both'),
    ('Comunik CRM',                     'both'),
    ('Coolwave',                        'supplier'),
    ('Coperato',                        'customer'),
    ('DCI Telecom',                     'customer'),
    ('Deutsche Telekom',                'both'),
    ('Diabolocom',                      'both'),
    ('Dialtel',                         'both'),
    ('DID Logic',                       'both'),
    ('Eastberry',                       'customer'),
    ('Eden-corporation',                'customer'),
    ('Eritel',                          'supplier'),
    ('Evoicebd Limited',                'customer'),
    ('Evox',                            'both'),
    ('Execallnet SRO',                  'both'),
    ('Fink Telecom',                    'customer'),
    ('Fjord Telecom',                   'both'),
    ('Flexo Telecom',                   'customer'),
    ('Freezvon',                        'customer'),
    ('Glance Telecom',                  'customer'),
    ('Global Carrier',                  'both'),
    ('Global Telivoz',                  'customer'),
    ('Globalfone',                      'both'),
    ('Globalnet Holdings',              'both'),
    ('Globe Teleservices',              'both'),
    ('Globtel',                         'both'),
    ('Go 4 Mobility',                   'both'),
    ('GoMobit',                         'customer'),
    ('Grifinum',                        'both'),
    ('Haloma Invest Ltd',               'customer'),
    ('Iberia',                          'both'),
    ('Illyvoip',                        'customer'),
    ('Im Solution',                     'both'),
    ('Infinitel Maris',                 'both'),
    ('Infinity Telecom',                'customer'),
    ('Inspire Communications',          'both'),
    ('Intellinet BV',                   'both'),
    ('Interconnect GR',                 'both'),
    ('IT Decision',                     'both'),
    ('Itnio Tech',                      'both'),
    ('Ixo Finland',                     'both'),
    ('Jiaxing',                         'both'),
    ('Jigsawtel',                       'both'),
    ('KPN',                             'supplier'),
    ('Landing Point',                   'customer'),
    ('Icon Global Services Limited',    'customer'),
    ('Lensol',                          'both'),
    ('Letsdial',                        'both'),
    ('Lexico',                          'both'),
    ('LMC Carrier',                     'both'),
    ('Lotus',                           'customer'),
    ('Magik Telecom',                   'both'),
    ('Manifone',                        'both'),
    ('Mediasat',                        'supplier'),
    ('Mediatel',                        'both'),
    ('Meratalk',                        'customer'),
    ('Microtalk',                       'both'),
    ('Midas Carrier',                   'customer'),
    ('MMD Smart',                       'both'),
    ('Munitel',                         'both'),
    ('Netswisstelecom',                 'both'),
    ('Network Creative Solutions',      'customer'),
    ('Network 9',                       'customer'),
    ('Nexlink Telecom',                 'customer'),
    ('Novametro',                       'both'),
    ('Novatel',                         'both'),
    ('NXCloud',                         'both'),
    ('Omag Info',                       'customer'),
    ('Omegatelecom',                    'customer'),
    ('One Albania',                     'both'),
    ('One Step',                        'customer'),
    ('Onextel',                         'both'),
    ('Orion Telekom',                   'both'),
    ('Orphy Telecom',                   'both'),
    ('Ourkom',                          'customer'),
    ('Oxnpgroup',                       'both'),
    ('Paasoo',                          'both'),
    ('Peoplefone',                      'both'),
    ('Premiumcom',                      'customer'),
    ('Premiumy',                        'both'),
    ('Primetel',                        'both'),
    ('Progressive Telecom',             'customer'),
    ('Purple Stone',                    'both'),
    ('QBR Telecom',                     'customer'),
    ('Quickcomtel',                     'both'),
    ('Rain Communication',              'customer'),
    ('Ray USA',                         'customer'),
    ('Reventix',                        'both'),
    ('Rigglotel Limited',               'supplier'),
    ('Ringolink',                       'customer'),
    ('Rocket Connect OU',               'both'),
    ('Saif Global',                     'both'),
    ('Salam',                           'both'),
    ('Serbway',                         'both'),
    ('Sewan',                           'both'),
    ('SLine',                           'both'),
    ('SMA Telecoms',                    'customer'),
    ('Smartbiz',                        'both'),
    ('Smarted Ltd',                     'customer'),
    ('SMSALA',                          'customer'),
    ('Softtop Limited',                 'customer'),
    ('Sparrow',                         'customer'),
    ('Speedflow',                       'both'),
    ('Squad Telecom',                   'customer'),
    ('Squaretalk',                      'customer'),
    ('Suiss Universe Services',         'both'),
    ('Surf Telecom',                    'both'),
    ('SVM Telecom',                     'both'),
    ('Swan',                            'both'),
    ('Swiftnet',                        'supplier'),
    ('Swisscom',                        'both'),
    ('Sync Sound',                      'customer'),
    ('Talk2All Telecom',                'customer'),
    ('Tapvox',                          'customer'),
    ('Telecom Business Systems America LLC', 'customer'),
    ('TDNT',                            'both'),
    ('Tech Open Systems',               'both'),
    ('Tech Services',                   'customer'),
    ('Techtown',                        'customer'),
    ('Telcodrome',                      'both'),
    ('Telecall',                        'both'),
    ('Telegra',                         'both'),
    ('TelePars',                        'customer'),
    ('Telesense',                       'both'),
    ('Telfon',                          'customer'),
    ('Telihub',                         'customer'),
    ('Telintel',                        'both'),
    ('Teliqon',                         'customer'),
    ('Telkart',                         'customer'),
    ('Thunder Telecom',                 'customer'),
    ('Toll Free Forwarding',            'both'),
    ('Tonerro',                         'both'),
    ('TSG Carrier',                     'customer'),
    ('Ubicentrex',                      'both'),
    ('UCloud',                          'both'),
    ('Universal Call',                  'both'),
    ('Vacotel',                         'both'),
    ('VAZQ Communications',             'both'),
    ('Ventatelecom',                    'both'),
    ('Virtual Call',                    'both'),
    ('Vodafone Idea',                   'both'),
    ('Voipboxx',                        'customer'),
    ('Voiped',                          'both'),
    ('Vonip',                           'both'),
    ('Voxbridge',                       'both'),
    ('Voxiis',                          'both'),
    ('Voximplant',                      'both'),
    ('VX-Telecom',                      'both'),
    ('WIC Worldcom',                    'both'),
    ('Worldcall Telecom',               'both'),
    ('Xicomm',                          'both'),
    ('Xinix',                           'both'),
    ('YIPL GmbH',                       'customer'),
    ('Yuboto',                          'both'),
    ('Zenit Telecom',                   'both'),
    ('Zonevoice',                       'customer'),
    ('Zoom Call Center',                'customer'),
]


class Command(BaseCommand):
    help = 'Import companies from Springboard ASA carrier list'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        created = 0
        skipped = 0

        for name, role in COMPANIES:
            if dry_run:
                exists = Company.objects.filter(name__iexact=name).exists()
                self.stdout.write(f'  {"EXISTS" if exists else "CREATE"}: {name} ({role})')
                if not exists:
                    created += 1
                else:
                    skipped += 1
            else:
                obj, was_created = Company.objects.get_or_create(
                    name=name,
                    defaults={'role': role, 'currency': 'USD', 'is_active': True},
                )
                if was_created:
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f'  Created: {name}'))
                else:
                    skipped += 1
                    self.stdout.write(f'  Skipped (exists): {name}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done — {created} created, {skipped} already existed.'
        ))
