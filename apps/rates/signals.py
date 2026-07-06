"""
Audit signals for Rate and Tariff — records every create/update/delete
to AuditLog so there is a full pricing change history.
"""
import json
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.forms.models import model_to_dict

from .models import Rate, Tariff, AuditLog

# Thread-local store so pre_save can pass the before-state to post_save
import threading
_state = threading.local()


def _snapshot(instance):
    """Serialise a model instance to a JSON string."""
    try:
        d = model_to_dict(instance)
        return json.dumps({k: str(v) for k, v in d.items()})
    except Exception:
        return '{}'


# ── Rate signals ──────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Rate)
def rate_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            _state.rate_before = _snapshot(Rate.objects.get(pk=instance.pk))
        except Rate.DoesNotExist:
            _state.rate_before = '{}'
    else:
        _state.rate_before = '{}'


@receiver(post_save, sender=Rate)
def rate_post_save(sender, instance, created, **kwargs):
    AuditLog.objects.create(
        object_type='Rate',
        object_id=instance.pk,
        object_repr=str(instance),
        action=AuditLog.ACTION_CREATE if created else AuditLog.ACTION_UPDATE,
        before_json=getattr(_state, 'rate_before', '{}'),
        after_json=_snapshot(instance),
    )


@receiver(post_delete, sender=Rate)
def rate_post_delete(sender, instance, **kwargs):
    AuditLog.objects.create(
        object_type='Rate',
        object_id=instance.pk,
        object_repr=str(instance),
        action=AuditLog.ACTION_DELETE,
        before_json=_snapshot(instance),
        after_json='{}',
    )


# ── Tariff signals ────────────────────────────────────────────────────────────

@receiver(pre_save, sender=Tariff)
def tariff_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            _state.tariff_before = _snapshot(Tariff.objects.get(pk=instance.pk))
        except Tariff.DoesNotExist:
            _state.tariff_before = '{}'
    else:
        _state.tariff_before = '{}'


@receiver(post_save, sender=Tariff)
def tariff_post_save(sender, instance, created, **kwargs):
    AuditLog.objects.create(
        object_type='Tariff',
        object_id=instance.pk,
        object_repr=str(instance),
        action=AuditLog.ACTION_CREATE if created else AuditLog.ACTION_UPDATE,
        before_json=getattr(_state, 'tariff_before', '{}'),
        after_json=_snapshot(instance),
    )


@receiver(post_delete, sender=Tariff)
def tariff_post_delete(sender, instance, **kwargs):
    AuditLog.objects.create(
        object_type='Tariff',
        object_id=instance.pk,
        object_repr=str(instance),
        action=AuditLog.ACTION_DELETE,
        before_json=_snapshot(instance),
        after_json='{}',
    )
