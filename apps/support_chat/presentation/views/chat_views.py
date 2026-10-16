from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.views import View

from apps.collaborators.models import WorkshopMember
from apps.support_chat.application.session_resolver import SessionResolver
from apps.support_chat.infrastructure.chat_hunter_client import ChatHunterClient
from apps.support_chat.infrastructure.errors import ChatHunterError
from apps.support_chat.infrastructure.history_parser import parse_atualizado_em, parse_history_payload, parse_titles_payload
from apps.support_chat.models import ChatSession
from apps.workshops.util.workshops import get_active_workshop_or_404

SESSION_LIST_LIMIT = 10
RATE_LIMIT_PER_MINUTE = 30
HISTORY_CACHE_SECONDS = 60


class SupportChatAuthMixin(LoginRequiredMixin):
    def handle_no_permission(self) -> JsonResponse:
        return JsonResponse({"detail": "Você não tem acesso ao chat nesta oficina."}, status=403)


def _resolve_member_and_workshop(request) -> tuple[Any, Any]:
    try:
        workshop = get_active_workshop_or_404(request)
    except Http404 as exc:
        raise ChatHunterError(status=403, message="Você não tem acesso ao chat nesta oficina.") from exc
    try:
        member = WorkshopMember.objects.get(user=request.user, workshop=workshop, is_active=True)
    except WorkshopMember.DoesNotExist as exc:
        raise ChatHunterError(status=403, message="Você não tem acesso ao chat nesta oficina.") from exc
    from apps.support_chat.application.access_policy import can_use_chat

    if not can_use_chat(user=request.user, workshop=workshop):
        raise ChatHunterError(status=403, message="Você não tem acesso ao chat nesta oficina.")
    return member, workshop


def _check_enabled() -> None:
    if not getattr(settings, "SUPPORT_CHAT_ENABLED", False):
        raise ChatHunterError(status=503, message="O assistente está desativado no momento.")


def _check_rate_limit(*, member_id: int) -> None:
    key = f"support_chat_rl:{member_id}"
    try:
        count = cache.get(key, 0)
        if count >= RATE_LIMIT_PER_MINUTE:
            raise ChatHunterError(status=429, message="Você enviou muitas mensagens. Aguarde um minuto.")
        cache.set(key, count + 1, 60)
    except ChatHunterError:
        raise
    except Exception:
        pass


def _history_cache_key(*, member_id: int, session_id: str) -> str:
    return f"support_chat_hist:{member_id}:{session_id}"


def _fetch_history(*, client: ChatHunterClient, member, workshop, user_id: int, session_id: str) -> dict[str, Any]:
    cache_key = _history_cache_key(member_id=member.pk, session_id=session_id)
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    payload = client.get_history(workshop_id=workshop.pk, user_id=user_id, session_id=session_id)
    messages = parse_history_payload(payload)
    result = {
        "messages": [{"role": m.role, "text": m.text} for m in messages],
        "atualizado_em": parse_atualizado_em(payload),
    }
    try:
        cache.set(cache_key, result, HISTORY_CACHE_SECONDS)
    except Exception:
        pass
    return result


class SupportChatBootstrapView(SupportChatAuthMixin, View):
    def get(self, request) -> JsonResponse:
        try:
            _check_enabled()
            member, workshop = _resolve_member_and_workshop(request)
            session = SessionResolver.resolve_active(member=member, workshop=workshop)
            client = ChatHunterClient()
            try:
                history = _fetch_history(client=client, member=member, workshop=workshop, user_id=request.user.pk, session_id=session.session_id)
            except ChatHunterError:
                history = {"messages": [], "atualizado_em": ""}
            return JsonResponse({"session_id": session.session_id, **history})
        except ChatHunterError as exc:
            return JsonResponse({"detail": exc.message}, status=exc.status)


class SupportChatAskView(SupportChatAuthMixin, View):
    def post(self, request) -> JsonResponse:
        try:
            _check_enabled()
            member, workshop = _resolve_member_and_workshop(request)
            _check_rate_limit(member_id=member.pk)
            try:
                body = json.loads(request.body.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                return JsonResponse({"detail": "Mensagem inválida."}, status=422)
            pergunta = str(body.get("pergunta") or "").strip()
            if not pergunta:
                return JsonResponse({"detail": "Digite uma mensagem."}, status=422)
            if len(pergunta) > 2000:
                return JsonResponse({"detail": "Mensagem muito longa (máximo 2000 caracteres)."}, status=422)
            requested_session = str(body.get("session_id") or "").strip()
            if requested_session:
                session = ChatSession.objects.filter(member=member, workshop=workshop, session_id=requested_session).first()
                if session is None:
                    session = SessionResolver.resolve_active(member=member, workshop=workshop)
            else:
                session = SessionResolver.resolve_active(member=member, workshop=workshop)
            client = ChatHunterClient()
            try:
                data = client.ask(
                    workshop_id=workshop.pk,
                    user_id=request.user.pk,
                    pergunta=pergunta,
                    session_id=session.session_id,
                )
            except ChatHunterError as exc:
                return JsonResponse({"detail": exc.message, "session_id": session.session_id}, status=exc.status)
            resposta = str(data.get("resposta") or data.get("answer") or "").strip()
            if not resposta:
                return JsonResponse(
                    {"detail": "O assistente não retornou resposta. Tente novamente.", "session_id": session.session_id},
                    status=502,
                )
            session.touch()
            try:
                cache.delete(_history_cache_key(member_id=member.pk, session_id=session.session_id))
                cache.delete(f"support_chat_titles:{member.pk}")
            except Exception:
                pass
            return JsonResponse({"resposta": resposta, "session_id": session.session_id})
        except ChatHunterError as exc:
            return JsonResponse({"detail": exc.message}, status=exc.status)


class SupportChatSessionsView(SupportChatAuthMixin, View):
    def get(self, request) -> JsonResponse:
        try:
            _check_enabled()
            member, workshop = _resolve_member_and_workshop(request)
            sessions = list(
                ChatSession.objects.filter(member=member, workshop=workshop).order_by("-last_interaction_at")[:SESSION_LIST_LIMIT]
            )
            return JsonResponse(
                {
                    "sessions": [
                        {
                            "session_id": s.session_id,
                            "last_interaction_at": s.last_interaction_at.isoformat(),
                            "is_active": s.is_active,
                        }
                        for s in sessions
                    ]
                }
            )
        except ChatHunterError as exc:
            return JsonResponse({"detail": exc.message}, status=exc.status)


class SupportChatNewSessionView(SupportChatAuthMixin, View):
    def post(self, request) -> JsonResponse:
        try:
            _check_enabled()
            member, workshop = _resolve_member_and_workshop(request)
            session = SessionResolver.create_new(member=member, workshop=workshop)
            try:
                cache.delete(f"support_chat_titles:{member.pk}")
            except Exception:
                pass
            return JsonResponse({"session_id": session.session_id, "messages": []})
        except ChatHunterError as exc:
            return JsonResponse({"detail": exc.message}, status=exc.status)


class SupportChatHistoryView(SupportChatAuthMixin, View):
    def get(self, request) -> JsonResponse:
        try:
            _check_enabled()
            member, workshop = _resolve_member_and_workshop(request)
            session_id = str(request.GET.get("session_id") or "").strip()
            if not session_id:
                return JsonResponse({"detail": "session_id é obrigatório."}, status=422)
            belongs = ChatSession.objects.filter(member=member, workshop=workshop, session_id=session_id).exists()
            if not belongs:
                return JsonResponse({"detail": "Sessão não encontrada."}, status=404)
            client = ChatHunterClient()
            try:
                history = _fetch_history(client=client, member=member, workshop=workshop, user_id=request.user.pk, session_id=session_id)
            except ChatHunterError as exc:
                return JsonResponse({"detail": exc.message}, status=exc.status)
            return JsonResponse({"session_id": session_id, **history})
        except ChatHunterError as exc:
            return JsonResponse({"detail": exc.message}, status=exc.status)


class SupportChatTitlesView(SupportChatAuthMixin, View):
    """Proxy do GET /api/v1/titles — lista de conversas do vínculo na oficina ativa."""

    def get(self, request) -> JsonResponse:
        try:
            _check_enabled()
            member, workshop = _resolve_member_and_workshop(request)
            cache_key = f"support_chat_titles:{member.pk}"
            cached = cache.get(cache_key)
            if isinstance(cached, dict):
                return JsonResponse(cached)
            client = ChatHunterClient()
            try:
                payload = client.get_titles(workshop_id=workshop.pk, user_id=request.user.pk)
            except ChatHunterError as exc:
                return JsonResponse({"detail": exc.message}, status=exc.status)
            result = {"titulos": parse_titles_payload(payload)}
            try:
                cache.set(cache_key, result, HISTORY_CACHE_SECONDS)
            except Exception:
                pass
            return JsonResponse(result)
        except ChatHunterError as exc:
            return JsonResponse({"detail": exc.message}, status=exc.status)
