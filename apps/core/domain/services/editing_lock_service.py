from __future__ import annotations

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from django.utils import timezone

from apps.core.infrastructure.models.editing_lock import EditingLock

LOCK_TIMEOUT_MINUTES = 5


def _get_content_type(obj: Model | str) -> ContentType:
    if isinstance(obj, str):
        app_label, model = obj.split(".", 1)
        return ContentType.objects.get_by_natural_key(app_label, model)
    return ContentType.objects.get_for_model(obj)


def acquire_lock(obj: Model, user, session_key: str, *, timeout_minutes: int = LOCK_TIMEOUT_MINUTES) -> tuple[bool, dict | None]:
    content_type = _get_content_type(obj)
    release_expired(timeout_minutes=timeout_minutes)

    existing = EditingLock.objects.filter(
        content_type=content_type,
        object_id=obj.pk,
    ).select_related("user").first()

    if existing:
        if existing.session_key == session_key:
            existing.locked_at = timezone.now()
            existing.save(update_fields=["locked_at"])
            return True, None
        return False, {
            "locked_by": existing.user.get_full_name() or existing.user.username,
            "locked_at": existing.locked_at.isoformat(),
        }

    EditingLock.objects.create(
        content_type=content_type,
        object_id=obj.pk,
        user=user,
        session_key=session_key,
    )
    return True, None


def release_lock(obj, session_key: str) -> bool:
    content_type = _get_content_type(obj)
    deleted, _ = EditingLock.objects.filter(
        content_type=content_type,
        object_id=obj.pk,
        session_key=session_key,
    ).delete()
    return deleted > 0


def get_lock_info(obj) -> dict | None:
    content_type = _get_content_type(obj)
    lock = EditingLock.objects.filter(
        content_type=content_type,
        object_id=obj.pk,
    ).select_related("user").first()

    if lock is None:
        return None

    return {
        "locked_by": lock.user.get_full_name() or lock.user.username,
        "locked_by_id": lock.user_id,
        "locked_by_session": lock.session_key,
        "locked_at": lock.locked_at.isoformat(),
    }


def release_expired(timeout_minutes: int = LOCK_TIMEOUT_MINUTES) -> int:
    cutoff = timezone.now() - timedelta(minutes=timeout_minutes)
    deleted, _ = EditingLock.objects.filter(locked_at__lt=cutoff).delete()
    return deleted


def refresh_lock(obj, session_key: str) -> bool:
    content_type = _get_content_type(obj)
    updated = EditingLock.objects.filter(
        content_type=content_type,
        object_id=obj.pk,
        session_key=session_key,
    ).update(locked_at=timezone.now())
    return updated > 0
