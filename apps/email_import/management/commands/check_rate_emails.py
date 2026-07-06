"""
check_rate_emails — Poll an IMAP mailbox and auto-import rate notification Excel files.

Reads IMAP connection from settings.RATE_IMPORT_IMAP.
For each active VendorEmailRule, checks the configured folder for unseen emails
from the rule's sender, applies optional subject/filename filters, downloads
the Excel attachment, and runs the rate import.

Usage:
    python manage.py check_rate_emails
    python manage.py check_rate_emails --dry-run   (import logic dry-run, still marks emails read)
    python manage.py check_rate_emails --limit 5   (process at most 5 emails per rule)
"""
import email
import imaplib
import os
import tempfile
import traceback
from email.header import decode_header

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.email_import.models import VendorEmailRule, RateImportLog


def _decode_str(value):
    """Decode an email header value (may be encoded)."""
    if not value:
        return ''
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ''.join(result)


def _get_imap_config():
    cfg = getattr(settings, 'RATE_IMPORT_IMAP', {})
    if not cfg:
        raise CommandError(
            'RATE_IMPORT_IMAP is not configured in settings.py.\n'
            'Add:\n'
            'RATE_IMPORT_IMAP = {\n'
            '    "HOST": "imap.example.com",\n'
            '    "PORT": 993,\n'
            '    "USERNAME": "rates@yourdomain.com",\n'
            '    "PASSWORD": "yourpassword",\n'
            '    "USE_SSL": True,\n'
            '}'
        )
    return cfg


def _connect(cfg):
    if cfg.get('USE_SSL', True):
        conn = imaplib.IMAP4_SSL(cfg['HOST'], cfg.get('PORT', 993))
    else:
        conn = imaplib.IMAP4(cfg['HOST'], cfg.get('PORT', 143))
    conn.login(cfg['USERNAME'], cfg['PASSWORD'])
    return conn


def _get_attachments(msg):
    """Yield (filename, bytes_data) for all Excel attachments in an email."""
    for part in msg.walk():
        content_disposition = part.get('Content-Disposition', '')
        if 'attachment' not in content_disposition and 'inline' not in content_disposition:
            # Also check for Excel parts without explicit Content-Disposition
            ct = part.get_content_type()
            if ct not in (
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-excel',
                'application/octet-stream',
            ):
                continue
        filename = part.get_filename()
        if not filename:
            continue
        filename = _decode_str(filename)
        if not filename.lower().endswith(('.xlsx', '.xls')):
            continue
        data = part.get_payload(decode=True)
        if data:
            yield filename, data


class Command(BaseCommand):
    help = 'Poll IMAP inbox for rate notification emails and auto-import them.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Run import in dry-run mode (no DB writes for rates).')
        parser.add_argument('--limit', type=int, default=20,
                            help='Max emails to process per rule (default: 20).')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit   = options['limit']

        cfg = _get_imap_config()
        rules = VendorEmailRule.objects.filter(is_active=True).select_related('tariff')

        if not rules.exists():
            self.stdout.write('No active VendorEmailRules found. Add rules in the UI.')
            return

        self.stdout.write(f'Connecting to {cfg["HOST"]}…')
        try:
            conn = _connect(cfg)
        except Exception as e:
            raise CommandError(f'IMAP connection failed: {e}')

        self.stdout.write(self.style.SUCCESS('Connected.'))

        try:
            for rule in rules:
                self.stdout.write(f'\n─── Rule: {rule.name} (folder: {rule.imap_folder}) ───')
                self._process_rule(conn, rule, dry_run, limit)
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS('\nDone.'))

    def _process_rule(self, conn, rule, dry_run, limit):
        # Select folder
        try:
            status, data = conn.select(f'"{rule.imap_folder}"')
            if status != 'OK':
                self.stdout.write(self.style.WARNING(
                    f'  Could not select folder "{rule.imap_folder}": {data}'
                ))
                return
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Folder error: {e}'))
            return

        # Search for unseen emails from the sender
        search_criteria = f'(UNSEEN FROM "{rule.sender_email}")'
        try:
            status, msg_ids = conn.search(None, search_criteria)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Search failed: {e}'))
            return

        ids = msg_ids[0].split() if msg_ids[0] else []
        self.stdout.write(f'  Found {len(ids)} unseen email(s) from {rule.sender_email}')

        processed = 0
        for uid in ids[-limit:]:  # most recent first (ids are oldest-first, so we take last N)
            if processed >= limit:
                break
            self._process_email(conn, rule, uid, dry_run)
            processed += 1

    def _process_email(self, conn, rule, uid, dry_run):
        # Fetch the full email
        status, data = conn.fetch(uid, '(RFC822)')
        if status != 'OK' or not data or not data[0]:
            return

        raw = data[0][1]
        msg = email.message_from_bytes(raw)

        from_addr = _decode_str(msg.get('From', ''))
        subject   = _decode_str(msg.get('Subject', ''))

        self.stdout.write(f'  → Subject: {subject[:80]}')

        # Apply subject keyword filter
        if rule.subject_keyword and rule.subject_keyword.lower() not in subject.lower():
            self.stdout.write(f'    Skipped — subject does not contain "{rule.subject_keyword}"')
            RateImportLog.objects.create(
                rule=rule, email_from=from_addr, email_subject=subject,
                status=RateImportLog.STATUS_SKIPPED,
                error_message=f'Subject filter "{rule.subject_keyword}" not matched',
            )
            conn.store(uid, '+FLAGS', '\\Seen')
            return

        # Find matching Excel attachment
        matched_attachment = None
        for filename, data_bytes in _get_attachments(msg):
            if rule.attachment_pattern and rule.attachment_pattern.lower() not in filename.lower():
                continue
            matched_attachment = (filename, data_bytes)
            break  # use first match

        if not matched_attachment:
            self.stdout.write(f'    Skipped — no matching Excel attachment found')
            RateImportLog.objects.create(
                rule=rule, email_from=from_addr, email_subject=subject,
                status=RateImportLog.STATUS_SKIPPED,
                error_message='No matching Excel attachment found',
            )
            conn.store(uid, '+FLAGS', '\\Seen')
            return

        filename, data_bytes = matched_attachment
        self.stdout.write(f'    Processing attachment: {filename}')

        # Save to temp file and run import
        suffix = '.xlsx' if filename.lower().endswith('.xlsx') else '.xls'
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(data_bytes)
                tmp_path = tmp.name

            stats = self._run_import(tmp_path, rule.tariff, dry_run)

            log = RateImportLog.objects.create(
                rule=rule,
                email_from=from_addr,
                email_subject=subject,
                attachment_name=filename,
                status=RateImportLog.STATUS_SUCCESS,
                destinations_created  = stats.get('destinations_created', 0),
                std_rates_created     = stats.get('std_rates_created', 0),
                std_rates_updated     = stats.get('std_rates_updated', 0),
                origin_groups_created = stats.get('origin_groups_created', 0),
                origin_rates_created  = stats.get('origin_rates_created', 0),
                origin_rates_updated  = stats.get('origin_rates_updated', 0),
                skipped               = stats.get('skipped', 0),
            )
            self.stdout.write(self.style.SUCCESS(
                f'    ✓ Imported — {stats.get("std_rates_created", 0)} std rates, '
                f'{stats.get("origin_rates_created", 0)} origin rates'
            ))

        except Exception as e:
            err = traceback.format_exc()
            RateImportLog.objects.create(
                rule=rule, email_from=from_addr, email_subject=subject,
                attachment_name=filename,
                status=RateImportLog.STATUS_ERROR,
                error_message=err[:2000],
            )
            self.stdout.write(self.style.ERROR(f'    ✗ Error: {e}'))
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        # Mark email as read regardless of import outcome
        conn.store(uid, '+FLAGS', '\\Seen')

    def _run_import(self, xlsx_path, tariff, dry_run):
        """Run the rate notification import and return stats dict."""
        from apps.rates.management.commands.import_rate_notification import Command as ImportCmd
        from apps.core.models import Destination
        from apps.rates.models import Rate, OriginGroup, OriginDialcode

        import openpyxl
        from django.db import transaction

        cmd = ImportCmd()
        # Silence stdout from the sub-command
        import io
        cmd.stdout = io.StringIO()
        cmd.stderr = io.StringIO()
        cmd.style = self.style

        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        sheets = {s.lower(): s for s in wb.sheetnames}

        stats = {
            'destinations_created': 0, 'dialcodes_updated': 0,
            'std_rates_created': 0, 'std_rates_updated': 0,
            'origin_groups_created': 0, 'origin_dialcodes_created': 0,
            'origin_rates_created': 0, 'origin_rates_updated': 0,
            'skipped': 0,
        }

        with transaction.atomic():
            if 'dialcodes' in sheets:
                cmd._import_dialcodes(wb[sheets['dialcodes']], None, dry_run, stats)
            if 'prices' in sheets:
                cmd._import_standard_rates(wb[sheets['prices']], tariff, None, dry_run, stats)
            if 'origin based billing dialcodes' in sheets:
                cmd._import_origin_dialcodes(wb[sheets['origin based billing dialcodes']], None, dry_run, stats)
            if 'origin based billing prices' in sheets:
                cmd._import_origin_rates(wb[sheets['origin based billing prices']], tariff, None, dry_run, stats)
            if dry_run:
                transaction.set_rollback(True)

        wb.close()
        return stats
