"""
CDR Ingestion REST API
======================
Switches POST call detail records here. No Django session is involved —
authentication uses the per-switch api_token UUID.

Endpoint
--------
POST /api/cdr/ingest/

Headers
-------
Authorization: Token <switch-api-token-uuid>
Content-Type: application/json

Body (JSON array)
-----------------
[
  {
    "call_id":         "abc-123",          # required, unique call reference
    "ani":             "441234567890",     # caller number (A leg)
    "dnis":            "4420123456",       # dialled number (B leg)
    "start_time":      "2026-05-26T10:00:00Z",  # ISO 8601
    "answer_time":     "2026-05-26T10:00:02Z",  # null if unanswered
    "end_time":        "2026-05-26T10:02:35Z",
    "duration_sec":    155,               # total call duration
    "disconnect_cause": 16               # Q.850 cause code, optional
  },
  ...
]

Response
--------
200 OK  {"status": "ok", "created": N, "duplicate": M}
401     {"status": "error", "message": "..."}
400     {"status": "error", "message": "..."}
"""
import json
from datetime import datetime, timezone

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.models import Switch
from .models import CDR


def _parse_dt(value):
    """Parse ISO-8601 datetime string to aware datetime, or return None."""
    if not value:
        return None
    try:
        # Python 3.11+ handles Z natively; for 3.10 replace Z with +00:00
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def _authenticate(request):
    """
    Validate Authorization header and return the matching Switch, or None.

    Expected header:  Authorization: Token <uuid>
    """
    auth = request.headers.get('Authorization', '')
    if not auth.lower().startswith('token '):
        return None
    token_str = auth[6:].strip()
    try:
        switch = Switch.objects.get(api_token=token_str, is_active=True)
        return switch
    except (Switch.DoesNotExist, ValueError):
        return None


@csrf_exempt
@require_POST
def cdr_ingest(request):
    """Accept a JSON array of CDRs from a switch and store them."""
    # ── Authentication ────────────────────────────────────────────────────────
    switch = _authenticate(request)
    if switch is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid or missing token.'},
            status=401,
        )

    # ── Parse body ────────────────────────────────────────────────────────────
    try:
        records = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': 'Request body must be a JSON array.'},
            status=400,
        )

    if not isinstance(records, list):
        return JsonResponse(
            {'status': 'error', 'message': 'Expected a JSON array at root level.'},
            status=400,
        )

    # ── Ingest ────────────────────────────────────────────────────────────────
    created = 0
    duplicate = 0
    errors = []

    for idx, rec in enumerate(records):
        call_id = rec.get('call_id', '').strip()
        if not call_id:
            errors.append(f'Record {idx}: missing call_id — skipped.')
            continue

        start_time = _parse_dt(rec.get('start_time'))
        if start_time is None:
            errors.append(f'Record {idx} ({call_id}): missing/invalid start_time — skipped.')
            continue

        # Deduplicate: skip if we already have this call_id from this switch
        if CDR.objects.filter(call_id=call_id, switch=switch).exists():
            duplicate += 1
            continue

        CDR.objects.create(
            call_id=call_id,
            switch=switch,
            ani=rec.get('ani', '')[:30],
            dnis=rec.get('dnis', '')[:30],
            start_time=start_time,
            answer_time=_parse_dt(rec.get('answer_time')),
            end_time=_parse_dt(rec.get('end_time')),
            duration_sec=int(rec.get('duration_sec') or 0),
            disconnect_cause=rec.get('disconnect_cause'),
            # customer/supplier/destination/rates resolved by process_cdrs command
            is_processed=False,
        )
        created += 1

    response = {'status': 'ok', 'created': created, 'duplicate': duplicate}
    if errors:
        response['warnings'] = errors

    return JsonResponse(response)
