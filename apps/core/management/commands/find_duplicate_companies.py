"""
Find duplicate Company records.

Checks for:
  1. Exact name duplicates (case-insensitive)
  2. Near-duplicates (after stripping spaces/punctuation)

Usage:
    python manage.py find_duplicate_companies
"""
import re
from collections import defaultdict
from django.core.management.base import BaseCommand
from apps.core.models import Company


def _normalise(name):
    """Lowercase, collapse whitespace, strip punctuation."""
    name = name.lower().strip()
    name = re.sub(r'[\s\-_.,\']+', ' ', name)
    return name


class Command(BaseCommand):
    help = 'Find duplicate Company records'

    def handle(self, *args, **options):
        companies = list(Company.objects.values('id', 'name', 'role', 'is_active').order_by('name'))

        # Group by normalised name
        groups = defaultdict(list)
        for c in companies:
            groups[_normalise(c['name'])].append(c)

        dupes = {k: v for k, v in groups.items() if len(v) > 1}

        if not dupes:
            self.stdout.write(self.style.SUCCESS('No duplicates found.'))
            return

        self.stdout.write(self.style.WARNING(f'{len(dupes)} duplicate group(s) found:\n'))
        for norm, members in sorted(dupes.items()):
            self.stdout.write(f'  Key: "{norm}"')
            for m in members:
                self.stdout.write(
                    f'    ID {m["id"]:>5}  [{m["role"]:<10}]  '
                    f'{"active" if m["is_active"] else "inactive"}  '
                    f'"{m["name"]}"'
                )
            self.stdout.write('')
