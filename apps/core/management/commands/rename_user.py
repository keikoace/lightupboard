"""
One-shot: rename user ID 1 from whatever it is to 'theoace'.
Safe to delete this file after running.

Usage:
    python manage.py rename_user
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Rename user ID 1 to theoace'

    def handle(self, *args, **options):
        try:
            u = User.objects.get(pk=1)
            old = u.username
            u.username = 'theoace'
            u.email = 'mm@lightupnet.de'
            u.first_name = ''
            u.last_name = ''
            u.save()
            self.stdout.write(self.style.SUCCESS(
                f'Renamed "{old}" → "theoace"  (email: mm@lightupnet.de)'
            ))
        except User.DoesNotExist:
            self.stderr.write('No user with ID 1 found.')
