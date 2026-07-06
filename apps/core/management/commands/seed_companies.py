"""
Seeds the initial company, tariff and rate data.
Run once after migrate on a fresh database.

    py manage.py seed_companies
"""
import csv
import os
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Company
from apps.rates.models import Tariff, Rate
from apps.core.models import Destination


class Command(BaseCommand):
    help = 'Seed SLine (customer) and 3U Telecom (supplier) with tariffs and rates.'

    def handle(self, *args, **options):
        w = self.stdout.write

        with transaction.atomic():

            # ── Companies ─────────────────────────────────────────────────────
            sline, created = Company.objects.get_or_create(
                name='SLine',
                defaults={
                    'role':       'customer',
                    'currency':   'EUR',
                    'is_active':  True,
                }
            )
            w(f'{"Created" if created else "Exists"}: SLine (customer)')

            telecom, created = Company.objects.get_or_create(
                name='3U Telecom',
                defaults={
                    'role':       'supplier',
                    'currency':   'EUR',
                    'is_active':  True,
                }
            )
            w(f'{"Created" if created else "Exists"}: 3U Telecom (supplier)')

            # ── Sell tariff for SLine ─────────────────────────────────────────
            tariff, created = Tariff.objects.get_or_create(
                company=sline,
                name='SLine Sell Tariff',
                defaults={
                    'side':                    'sell',
                    'currency':                'EUR',
                    'effective_date':          date(2026, 1, 1),
                    'is_active':               True,
                    'default_billing_minimum': 1,
                    'default_billing_increment': 1,
                }
            )
            w(f'{"Created" if created else "Exists"}: SLine Sell Tariff (id={tariff.pk})')

            # ── Rates ─────────────────────────────────────────────────────────
            rate_data = [
                # Germany Mobile (0.020)
                ('49150','Germany Mobile','0.020000'),
                ('49151','Germany Mobile','0.020000'),
                ('49152','Germany Mobile','0.020000'),
                ('49153','Germany Mobile','0.020000'),
                ('49154','Germany Mobile','0.020000'),
                ('49155','Germany Mobile','0.020000'),
                ('49156','Germany Mobile','0.020000'),
                ('49157','Germany Mobile','0.020000'),
                ('49158','Germany Mobile','0.020000'),
                ('49159','Germany Mobile','0.020000'),
                ('49160','Germany Mobile','0.020000'),
                ('49162','Germany Mobile','0.020000'),
                ('49163','Germany Mobile','0.020000'),
                ('49170','Germany Mobile','0.020000'),
                ('49171','Germany Mobile','0.020000'),
                ('49172','Germany Mobile','0.020000'),
                ('49173','Germany Mobile','0.020000'),
                ('49174','Germany Mobile','0.020000'),
                ('49175','Germany Mobile','0.020000'),
                ('49176','Germany Mobile','0.020000'),
                ('49177','Germany Mobile','0.020000'),
                ('49178','Germany Mobile','0.020000'),
                ('49179','Germany Mobile','0.020000'),
                # Germany Fixed (0.012)
                ('490','Germany Fixed','0.012000'),
                ('4900','Germany Fixed','0.012000'),('4901','Germany Fixed','0.012000'),
                ('4902','Germany Fixed','0.012000'),('4903','Germany Fixed','0.012000'),
                ('4904','Germany Fixed','0.012000'),('4905','Germany Fixed','0.012000'),
                ('4906','Germany Fixed','0.012000'),('4907','Germany Fixed','0.012000'),
                ('4908','Germany Fixed','0.012000'),('4909','Germany Fixed','0.012000'),
                ('4920','Germany Fixed','0.012000'),('4921','Germany Fixed','0.012000'),
                ('4922','Germany Fixed','0.012000'),('4923','Germany Fixed','0.012000'),
                ('4924','Germany Fixed','0.012000'),('4925','Germany Fixed','0.012000'),
                ('4926','Germany Fixed','0.012000'),('4927','Germany Fixed','0.012000'),
                ('4928','Germany Fixed','0.012000'),('4929','Germany Fixed','0.012000'),
                ('4930','Germany Fixed','0.012000'),('4931','Germany Fixed','0.012000'),
                ('4932','Germany Fixed','0.012000'),('4933','Germany Fixed','0.012000'),
                ('4934','Germany Fixed','0.012000'),('4935','Germany Fixed','0.012000'),
                ('4936','Germany Fixed','0.012000'),('4937','Germany Fixed','0.012000'),
                ('4938','Germany Fixed','0.012000'),('4939','Germany Fixed','0.012000'),
                ('4940','Germany Fixed','0.012000'),('4941','Germany Fixed','0.012000'),
                ('4942','Germany Fixed','0.012000'),('4943','Germany Fixed','0.012000'),
                ('4944','Germany Fixed','0.012000'),('4945','Germany Fixed','0.012000'),
                ('4946','Germany Fixed','0.012000'),('4947','Germany Fixed','0.012000'),
                ('4948','Germany Fixed','0.012000'),('4949','Germany Fixed','0.012000'),
                ('4950','Germany Fixed','0.012000'),('4951','Germany Fixed','0.012000'),
                ('4952','Germany Fixed','0.012000'),('4953','Germany Fixed','0.012000'),
                ('4954','Germany Fixed','0.012000'),('4955','Germany Fixed','0.012000'),
                ('4956','Germany Fixed','0.012000'),('4957','Germany Fixed','0.012000'),
                ('4958','Germany Fixed','0.012000'),('4959','Germany Fixed','0.012000'),
                ('4960','Germany Fixed','0.012000'),('4961','Germany Fixed','0.012000'),
                ('4962','Germany Fixed','0.012000'),('4963','Germany Fixed','0.012000'),
                ('4964','Germany Fixed','0.012000'),('4965','Germany Fixed','0.012000'),
                ('4966','Germany Fixed','0.012000'),('4967','Germany Fixed','0.012000'),
                ('4968','Germany Fixed','0.012000'),('4969','Germany Fixed','0.012000'),
                ('4970','Germany Fixed','0.012000'),('4971','Germany Fixed','0.012000'),
                ('4972','Germany Fixed','0.012000'),('4973','Germany Fixed','0.012000'),
                ('4974','Germany Fixed','0.012000'),('4975','Germany Fixed','0.012000'),
                ('4976','Germany Fixed','0.012000'),('4977','Germany Fixed','0.012000'),
                ('4978','Germany Fixed','0.012000'),('4979','Germany Fixed','0.012000'),
                ('4980','Germany Fixed','0.012000'),('4981','Germany Fixed','0.012000'),
                ('4982','Germany Fixed','0.012000'),('4983','Germany Fixed','0.012000'),
                ('4984','Germany Fixed','0.012000'),('4985','Germany Fixed','0.012000'),
                ('4986','Germany Fixed','0.012000'),('4987','Germany Fixed','0.012000'),
                ('4988','Germany Fixed','0.012000'),('4989','Germany Fixed','0.012000'),
                ('4990','Germany Fixed','0.012000'),('4991','Germany Fixed','0.012000'),
                ('4992','Germany Fixed','0.012000'),('4993','Germany Fixed','0.012000'),
                ('4994','Germany Fixed','0.012000'),('4995','Germany Fixed','0.012000'),
                ('4996','Germany Fixed','0.012000'),('4997','Germany Fixed','0.012000'),
                ('4998','Germany Fixed','0.012000'),('4999','Germany Fixed','0.012000'),
                # Austria Mobile (0.025)
                ('4366','Austria Mobile','0.025000'),
                ('4367','Austria Mobile','0.025000'),
                ('4368','Austria Mobile','0.025000'),
                ('4369','Austria Mobile','0.025000'),
                # Austria Fixed (0.015)
                ('4312','Austria Fixed','0.015000'),('4313','Austria Fixed','0.015000'),
                ('4314','Austria Fixed','0.015000'),('4315','Austria Fixed','0.015000'),
                ('4316','Austria Fixed','0.015000'),('4317','Austria Fixed','0.015000'),
                ('4318','Austria Fixed','0.015000'),('4319','Austria Fixed','0.015000'),
                ('4321','Austria Fixed','0.015000'),('4322','Austria Fixed','0.015000'),
                ('4323','Austria Fixed','0.015000'),('4325','Austria Fixed','0.015000'),
                ('4326','Austria Fixed','0.015000'),('4327','Austria Fixed','0.015000'),
                ('4328','Austria Fixed','0.015000'),('4331','Austria Fixed','0.015000'),
                ('4333','Austria Fixed','0.015000'),('4334','Austria Fixed','0.015000'),
                ('4335','Austria Fixed','0.015000'),('4336','Austria Fixed','0.015000'),
                ('4337','Austria Fixed','0.015000'),('4338','Austria Fixed','0.015000'),
                ('4339','Austria Fixed','0.015000'),('4341','Austria Fixed','0.015000'),
                ('4342','Austria Fixed','0.015000'),('4343','Austria Fixed','0.015000'),
                ('4345','Austria Fixed','0.015000'),('4346','Austria Fixed','0.015000'),
                ('4347','Austria Fixed','0.015000'),('4348','Austria Fixed','0.015000'),
                ('4350','Austria Fixed','0.015000'),('4351','Austria Fixed','0.015000'),
                ('4352','Austria Fixed','0.015000'),('4353','Austria Fixed','0.015000'),
                ('4354','Austria Fixed','0.015000'),('4355','Austria Fixed','0.015000'),
                ('4357','Austria Fixed','0.015000'),('4365','Austria Fixed','0.015000'),
                ('4370','Austria Fixed','0.015000'),('4372','Austria Fixed','0.015000'),
                ('4373','Austria Fixed','0.015000'),('4374','Austria Fixed','0.015000'),
                ('4376','Austria Fixed','0.015000'),('4377','Austria Fixed','0.015000'),
                ('4378','Austria Fixed','0.015000'),('4379','Austria Fixed','0.015000'),
            ]

            # Find destination for each prefix (longest match)
            prefix_map = {d.prefix: d for d in Destination.objects.filter(is_active=True)}

            def match_dest(prefix):
                for length in range(len(prefix), 0, -1):
                    if prefix[:length] in prefix_map:
                        return prefix_map[prefix[:length]]
                return None

            created_rates = 0
            for prefix, dest_name, rate in rate_data:
                dest = match_dest(prefix)
                _, c = Rate.objects.get_or_create(
                    tariff=tariff,
                    prefix=prefix,
                    effective_date=date(2026, 1, 1),
                    defaults={
                        'destination':          dest or Destination.objects.first(),
                        'rate_per_minute':      rate,
                        'minimum_duration_sec': 1,
                        'billing_increment_sec':1,
                    }
                )
                if c:
                    created_rates += 1

            w(self.style.SUCCESS(
                f'\nDone.\n'
                f'  Rates created : {created_rates}\n'
                f'  Rates skipped : {len(rate_data) - created_rates} (already existed)\n'
                f'\nNow run: py manage.py process_cdrs'
            ))
