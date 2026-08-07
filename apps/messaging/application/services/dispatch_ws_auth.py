from __future__ import annotations

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

from apps.messaging.models import MessageDispatchBatch

_DISPATCH_WS_SALT = "messaging.dispatch.ws"
_DISPATCH_WS_MAX_AGE_SECONDS = 60 * 60 * 12  # 12 hours


class DispatchWebSocketAuthError(Exception):
    pass


def issue_dispatch_ws_token(*, user_id: int, workshop_id: int) -> str:
    signer = TimestampSigner(salt=_DISPATCH_WS_SALT)
    return signer.sign(f"{int(user_id)}:{int(workshop_id)}")


def verify_dispatch_ws_token(token: str) -> tuple[int, int]:
    """Return (user_id, workshop_id) from a signed WS token."""
    raw = str(token or "").strip()
    if not raw:
        raise DispatchWebSocketAuthError("Token ausente.")

    signer = TimestampSigner(salt=_DISPATCH_WS_SALT)
    try:
        value = signer.unsign(raw, max_age=_DISPATCH_WS_MAX_AGE_SECONDS)
    except SignatureExpired as exc:
        raise DispatchWebSocketAuthError("Token expirado.") from exc
    except BadSignature as exc:
        raise DispatchWebSocketAuthError("Token inválido.") from exc

    try:
        user_id_str, workshop_id_str = value.split(":", 1)
        return int(user_id_str), int(workshop_id_str)
    except ValueError as exc:
        raise DispatchWebSocketAuthError("Token malformado.") from exc


def token_can_access_dispatch_batch(*, user_id: int, workshop_id: int, batch_id: int) -> bool:
    from apps.accounts.models import User
    from apps.collaborators.models import WorkshopMember

    try:
        batch = MessageDispatchBatch.objects.get(pk=batch_id)
    except MessageDispatchBatch.DoesNotExist:
        return False

    if batch.workshop_id != workshop_id:
        return False

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return False

    if getattr(user, "is_superuser", False):
        return True

    return WorkshopMember.objects.filter(user_id=user_id, workshop_id=workshop_id).exists()
