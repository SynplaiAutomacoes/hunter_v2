from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.budget.approval import BudgetApprovalError, approve_budget_with_stock
from apps.budget.models import Budget, BudgetStatus


logger = logging.getLogger(__name__)


def _extract_event(payload: dict) -> str:
    for key in ("event", "type", "name"):
        value = payload.get(key)
        if isinstance(value, str):
            return value.upper()
    return ""


def _extract_envelope_id(payload: dict) -> str:
    direct = payload.get("envelopeId") or payload.get("envelope_id")
    if isinstance(direct, str):
        return direct

    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get("envelopeId") or data.get("envelope_id")
        if isinstance(nested, str):
            return nested

    return ""


@method_decorator(csrf_exempt, name="dispatch")
class SuperSignWebhookView(View):
    def post(self, request):
        auth_header = request.headers.get("Authorization", "")
        expected_api_key = getattr(settings, "SUPERSIGN_API_KEY", "")
        expected_auth = f"Bearer {expected_api_key}" if expected_api_key else ""
        if not expected_auth or auth_header != expected_auth:
            return JsonResponse({"error": "invalid_authorization"}, status=403)

        account_id = request.headers.get("x-account-id", "")
        expected_account_id = getattr(settings, "SUPERSIGN_ACCOUNT_ID", "")
        if expected_account_id and account_id and account_id != expected_account_id:
            return JsonResponse({"error": "invalid_account"}, status=403)

        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid_json"}, status=400)

        event_name = _extract_event(payload)
        envelope_id = _extract_envelope_id(payload)

        if not envelope_id:
            logger.warning("Webhook recebido sem envelope_id", extra={"event": event_name})
            return HttpResponse(status=200)

        budget = Budget.objects.filter(signature_external_id=envelope_id).first()
        if budget is None:
            logger.info("Webhook sem budget correspondente", extra={"event": event_name, "envelope_id": envelope_id})
            return HttpResponse(status=200)

        if event_name != "ENVELOPE_COMPLETED":
            logger.info("Evento ignorado", extra={"event": event_name, "budget_id": budget.pk})
            return HttpResponse(status=200)

        if budget.status == BudgetStatus.APPROVED:
            return HttpResponse(status=200)

        try:
            approve_budget_with_stock(budget=budget, user=None)
        except BudgetApprovalError as exc:
            logger.warning("Falha de regra ao aprovar por webhook", extra={"budget_id": budget.pk, "error": str(exc)})
            return JsonResponse({"error": str(exc)}, status=409)
        except Exception:
            logger.exception("Erro interno ao processar webhook", extra={"budget_id": budget.pk, "envelope_id": envelope_id})
            return HttpResponse(status=500)

        return HttpResponse(status=200)
