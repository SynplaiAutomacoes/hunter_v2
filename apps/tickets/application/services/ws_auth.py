from __future__ import annotations

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

from apps.tickets.models import Ticket
from apps.tickets.permissions import can_view_ticket

_TICKET_CHAT_WS_SALT = "tickets.chat.ws"
_TICKET_CHAT_WS_MAX_AGE_SECONDS = 60 * 60 * 12


class TicketChatWebSocketAuthError(Exception):
    pass


def issue_ticket_chat_ws_token(*, user_id: int, ticket_id: int) -> str:
    signer = TimestampSigner(salt=_TICKET_CHAT_WS_SALT)
    return signer.sign(f"{int(user_id)}:{int(ticket_id)}")


def verify_ticket_chat_ws_token(token: str) -> tuple[int, int]:
    raw = str(token or "").strip()
    if not raw:
        raise TicketChatWebSocketAuthError("Token ausente.")

    signer = TimestampSigner(salt=_TICKET_CHAT_WS_SALT)
    try:
        value = signer.unsign(raw, max_age=_TICKET_CHAT_WS_MAX_AGE_SECONDS)
    except SignatureExpired as exc:
        raise TicketChatWebSocketAuthError("Token expirado.") from exc
    except BadSignature as exc:
        raise TicketChatWebSocketAuthError("Token inválido.") from exc

    try:
        user_id_str, ticket_id_str = value.split(":", 1)
        return int(user_id_str), int(ticket_id_str)
    except ValueError as exc:
        raise TicketChatWebSocketAuthError("Token malformado.") from exc


def token_can_access_ticket_chat(*, user_id: int, ticket_id: int) -> bool:
    from apps.accounts.models import User

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
        user = User.objects.get(pk=user_id)
    except (Ticket.DoesNotExist, User.DoesNotExist):
        return False

    return can_view_ticket(user=user, ticket=ticket)
