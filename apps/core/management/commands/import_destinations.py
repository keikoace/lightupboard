import csv
import zipfile
import os
from django.core.management.base import BaseCommand, CommandError
from apps.core.models import Destination


class Command(BaseCommand):
    help = 'Import destinations from Springboard dial codes ZIP export'

    def add_arguments(self, parser):
        parser.add_argument(
            'zip_file',
            nargs='?',
            default=os.path.join(os.path.expanduser('~'), 'Downloads', 'milos_light_20260526_101319.zip'),
            help='Path to the Springboard codes ZIP file',
        )

    def handle(self, *args, **options):
        zip_path = options['zip_file']

        if not os.path.exists(zip_path):
            raise CommandError(
                f'File not found: {zip_path}\n'
                'Download it from Springboard → Setup → Destinations → Codes CSV Export'
            )

        self.stdout.write(f'Reading: {zip_path}')

        # CSV columns: id, country, destination_name, prefix, full_name, date, status
        # One Destination per unique name, using the shortest prefix as primary
        dest_map = {}

        with zipfile.ZipFile(zip_path) as zf:
            csv_name = [n for n in zf.namelist() if n.endswith('.csv')][0]
            with zf.open(csv_name) as f:
                reader = csv.reader(line.decode('latin-1') for line in f)
                for row in reader:
                    if len(row) < 7:
                        continue
                    _, country, dest_name, prefix, _, _, status = row[:7]
                    country = country.strip().strip('"')
                    dest_name = dest_name.strip().strip('"')
                    prefix = prefix.strip().strip('"')
                    status = status.strip().strip('"')

                    if not dest_name or not prefix or not prefix.isdigit():
                        continue

                    is_active = status.lower() == 'open'
                    if dest_name not in dest_map:
                        dest_map[dest_name] = {
                            'name': dest_name,
                            'country': country,
                            'prefix': prefix,
                            'is_active': is_active,
                        }
                    else:
                        # Keep shortest prefix (most general)
                        if len(prefix) < len(dest_map[dest_name]['prefix']):
                            dest_map[dest_name]['prefix'] = prefix

        self.stdout.write(f'Found {len(dest_map)} unique destinations')

        created = updated = skipped = 0
        for dest_data in dest_map.values():
            try:
                _, c = Destination.objects.update_or_create(
                    prefix=dest_data['prefix'],
                    defaults={
                        'name': dest_data['name'],
                        'country': dest_data['country'],
                        'is_active': dest_data['is_active'],
                    }
                )
                if c:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                self.stderr.write(f"  Skipped {dest_data['name']}: {e}")
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done — {created} created, {updated} updated, {skipped} skipped'
        ))
