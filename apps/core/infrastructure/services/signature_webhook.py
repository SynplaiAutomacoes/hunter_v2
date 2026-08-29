from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement
from apps.workorder.approval import WorkOrderApprovalError, approve_workorder_with_stock
from apps.workorder.models import WorkOrder, WorkOrderError, WorkOrderStatus, WorkOrderWarrantyPlan


logger = logging.getLogger(__name__)


def _find_first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    queue: list[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                if key in keys and isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return ""


SIGNATURE_COMPLETED_EVENTS = frozenset(
    {
        "ENVELOPE_COMPLETED",
        "DOCUMENT_SIGNED",
        "DOCUMENT_COMPLETED",
        "ENVELOPE_COMPLETE",
        "SIGNED",
        "COMPLETED",
    }
)
SIGNATURE_DECLINED_EVENTS = frozenset(
    {
        "DOCUMENT_DECLINED",
        "DOCUMENT_DECLINE",
        "ENVELOPE_DECLINED",
        "DECLINED",
    }
)


def _normalize_event_name(raw_event: str) -> str:
    normalized = raw_event.strip().upper().replace(".", "_").replace("-", "_")
    if normalized in SIGNATURE_COMPLETED_EVENTS:
        return "ENVELOPE_COMPLETED"
    if normalized in SIGNATURE_DECLINED_EVENTS:
        return "DOCUMENT_DECLINED"
    return normalized


def extract_signature_event(payload: dict[str, Any], *, header_event: str = "") -> str:
    if header_event.strip():
        return _normalize_event_name(header_event)
    for key in ("event", "eventType", "type"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_event_name(value)
    raw_event = _find_first_string(payload, ("event", "eventType", "type"))
    if not raw_event:
        return ""
    return _normalize_event_name(raw_event)


def _payload_structure(payload: Any, depth: int = 0, max_depth: int = 3) -> str:
    if depth > max_depth:
        return "..."
    if isinstance(payload, dict):
        parts = []
        for key, value in payload.items():
            child = _payload_structure(value, depth + 1, max_depth)
            parts.append(f"{key}: {child}")
        return "{" + ", ".join(parts) + "}"
    if isinstance(payload, list):
        if not payload:
            return "[]"
        return "[" + _payload_structure(payload[0], depth + 1, max_depth) + (", ...]" if len(payload) > 1 else "]")
    return f"{type(payload).__name__}({len(str(payload))})"


def extract_signature_envelope_id(payload: dict[str, Any]) -> str:
    direct = _find_first_string(payload, ("envelopeId", "envelope_id", "envelopeID"))
    if direct:
        return direct

    queue: list[Any] = [payload]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            envelope_obj = current.get("envelope")
            if isinstance(envelope_obj, dict):
                envelope_id = envelope_obj.get("id")
                if isinstance(envelope_id, str) and envelope_id.strip():
                    return envelope_id.strip()
            for value in current.values():
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            queue.extend(current)
    return ""


def build_synplaisign_webhook_signature(*, body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _hmac_digest_hex(*, body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def validate_signature_webhook_hmac(*, body: bytes, secret: str, received_signature: str) -> bool:
    received = str(received_signature or "").strip()
    if received.lower().startswith("sha256="):
        received = received.split("=", 1)[1].strip()
    received = received.lower()
    expected = _hmac_digest_hex(body=body, secret=secret)
    if len(received) != len(expected):
        return False
    return hmac.compare_digest(expected, received)


def validate_signature_webhook_request(request: HttpRequest, *, workshop_secret: str = "") -> HttpResponse | None:
    """Validate HMAC using workshop secret, with optional global fallback."""
    secrets: list[str] = []
    for candidate in (workshop_secret, getattr(settings, "SYNPLAISIGN_WEBHOOK_SECRET", "")):
        normalized = str(candidate or "").strip()
        if normalized and normalized not in secrets:
            secrets.append(normalized)
    if not secrets:
        return None

    received = str(request.headers.get("x-synplai-signature") or "").strip()
    if not received:
        logger.warning("signature_webhook_missing_hmac", extra={"ip": request.META.get("REMOTE_ADDR")})
        return JsonResponse({"error": "invalid_signature"}, status=403)

    body = request.body or b""
    if any(validate_signature_webhook_hmac(body=body, secret=secret, received_signature=received) for secret in secrets):
        return None

    logger.warning("signature_webhook_hmac_failed", extra={"ip": request.META.get("REMOTE_ADDR")})
    return JsonResponse({"error": "invalid_signature"}, status=403)


def parse_signature_webhook_body(request: HttpRequest) -> dict[str, Any]:
    payload = json.loads(request.body or b"{}")
    return payload if isinstance(payload, dict) else {}


def _normalize_envelope_id(envelope_id: str) -> str:
    return str(envelope_id or "").strip()


def _signature_envelope_lookup(envelope_id: str) -> Q:
    normalized = _normalize_envelope_id(envelope_id)
    return Q(signature_external_id=normalized) | Q(signature_document_id=normalized)


def _find_term_signing(envelope_id: str):
    from apps.terms.models import BudgetTermSigning

    normalized = _normalize_envelope_id(envelope_id)
    if not normalized:
        return None

    return (
        BudgetTermSigning.objects.select_related("workshop")
        .filter(_signature_envelope_lookup(normalized))
        .first()
    )


def _resolve_workshop_for_envelope(envelope_id: str):
    from apps.budget.models import Budget

    normalized = _normalize_envelope_id(envelope_id)
    if not normalized:
        return None, None, None, None

    term_signing = _find_term_signing(normalized)
    if term_signing is not None:
        return term_signing.workshop, None, None, term_signing

    lookup = _signature_envelope_lookup(normalized)
    budget = Budget.objects.select_related("workshop").filter(lookup).first()
    if budget is not None:
        return budget.workshop, budget, None, None

    workorder = WorkOrder.objects.select_related("workshop").filter(lookup).first()
    if workorder is not None:
        return workorder.workshop, None, workorder, None
    return None, None, None, None


def _reject_budget_from_decline(*, budget, envelope_id: str) -> None:
    from apps.budget.models import BudgetStatus

    if budget.status == BudgetStatus.REJECTED:
        logger.info(
            "signature_webhook_budget_already_rejected",
            extra={"budget_id": budget.pk, "envelope_id": envelope_id},
        )
        return

    has_active_workorder = budget.workorders.exclude(status=WorkOrderStatus.CANCELLED).exists()
    if has_active_workorder:
        logger.info(
            "signature_webhook_budget_decline_skipped_active_workorder",
            extra={"budget_id": budget.pk, "envelope_id": envelope_id},
        )
        return

    if budget.is_status_locked:
        logger.info(
            "signature_webhook_budget_decline_skipped_locked",
            extra={"budget_id": budget.pk, "envelope_id": envelope_id, "status": budget.status},
        )
        return

    budget.status = BudgetStatus.REJECTED
    budget.save(update_fields=["status"])
    logger.info("signature_webhook_budget_rejected", extra={"budget_id": budget.pk, "envelope_id": envelope_id})


def _reject_workorder_from_decline(*, workorder, envelope_id: str) -> None:
    if workorder.status == WorkOrderStatus.REJECTED:
        logger.info(
            "signature_webhook_workorder_already_rejected",
            extra={"workorder_id": workorder.pk, "envelope_id": envelope_id},
        )
        return

    if workorder.is_status_locked:
        logger.info(
            "signature_webhook_workorder_decline_skipped_locked",
            extra={"workorder_id": workorder.pk, "envelope_id": envelope_id, "status": workorder.status},
        )
        return

    try:
        workorder.reject(reason="Documento recusado pelo signatário")
    except WorkOrderError:
        WorkOrder.objects.filter(pk=workorder.pk).update(signature_decline_pending=True)
        logger.info(
            "signature_webhook_workorder_decline_skipped_payments",
            extra={"workorder_id": workorder.pk, "envelope_id": envelope_id},
        )
        return
    logger.info("signature_webhook_workorder_rejected", extra={"workorder_id": workorder.pk, "envelope_id": envelope_id})


def _decline_term_signing(*, term_signing, envelope_id: str) -> None:
    from apps.terms.models import TermSignatureStatus

    if term_signing.signature_request_status == TermSignatureStatus.DECLINED:
        logger.info(
            "signature_webhook_term_already_declined",
            extra={"term_signing_id": term_signing.pk, "envelope_id": envelope_id},
        )
        return

    term_signing.mark_signature_declined()
    logger.info("signature_webhook_term_declined", extra={"term_signing_id": term_signing.pk, "envelope_id": envelope_id})


def _approve_term_signing(*, term_signing, envelope_id: str) -> None:
    from apps.terms.models import TermSignatureStatus

    if term_signing.signature_request_status == TermSignatureStatus.APPROVED:
        logger.info(
            "signature_webhook_term_already_approved",
            extra={"term_signing_id": term_signing.pk, "envelope_id": envelope_id},
        )
        return

    term_signing.mark_signature_approved()
    logger.info("signature_webhook_term_approved", extra={"term_signing_id": term_signing.pk, "envelope_id": envelope_id})


def process_signature_webhook_payload(*, payload: dict[str, Any], budget=None, workorder=None, term_signing=None, header_event: str = "") -> HttpResponse:
    from apps.budget.models import Budget, SignatureStatus
    from apps.workorder.models import WorkOrderSignatureStatus

    event_name = extract_signature_event(payload, header_event=header_event)
    envelope_id = _normalize_envelope_id(extract_signature_envelope_id(payload))
    logger.info(
        "signature_webhook_parsed",
        extra={"event": event_name, "envelope_id": envelope_id, "payload_structure": _payload_structure(payload)},
    )

    if not envelope_id:
        logger.warning("signature_webhook_missing_envelope_id", extra={"event": event_name, "payload_keys": list(payload.keys())})
        return HttpResponse(status=200)

    if budget is None and workorder is None and term_signing is None:
        term_signing = _find_term_signing(envelope_id)
        if term_signing is not None:
            budget = None
            workorder = None
        else:
            lookup = _signature_envelope_lookup(envelope_id)
            budget = Budget.objects.filter(lookup).first()
            workorder = WorkOrder.objects.filter(lookup).first()

    if term_signing is not None:
        try:
            if event_name == "DOCUMENT_DECLINED":
                _decline_term_signing(term_signing=term_signing, envelope_id=envelope_id)
                return HttpResponse(status=200)
            if event_name != "ENVELOPE_COMPLETED":
                logger.info(
                    "signature_webhook_event_ignored",
                    extra={"event": event_name, "term_signing_id": term_signing.pk},
                )
                return HttpResponse(status=200)
            _approve_term_signing(term_signing=term_signing, envelope_id=envelope_id)
        except Exception:
            logger.exception(
                "signature_webhook_term_processing_failed",
                extra={"term_signing_id": term_signing.pk, "envelope_id": envelope_id},
            )
            return HttpResponse(status=500)
        return HttpResponse(status=200)

    if budget is None and workorder is None:
        from apps.terms.models import BudgetTermSigning, TermSignatureStatus

        recent_budget = Budget.objects.filter(signature_request_status=SignatureStatus.SENT).order_by("-signature_sent_at").values("id", "signature_external_id", "signature_document_id", "signature_sent_at")[:3]
        recent_workorder = WorkOrder.objects.filter(signature_request_status=WorkOrderSignatureStatus.SENT).order_by("-signature_sent_at").values("id", "signature_external_id", "signature_document_id", "signature_sent_at")[:3]
        recent_term_signings = BudgetTermSigning.objects.filter(signature_request_status=TermSignatureStatus.SENT).order_by("-signature_sent_at").values(
            "id",
            "signature_external_id",
            "signature_document_id",
            "signature_sent_at",
        )[:3]
        logger.info(
            "signature_webhook_no_matching_document",
            extra={
                "event": event_name,
                "envelope_id": envelope_id,
                "recent_sent_budgets": list(recent_budget),
                "recent_sent_workorders": list(recent_workorder),
                "recent_sent_term_signings": list(recent_term_signings),
            },
        )
        return HttpResponse(status=200)

    if event_name == "DOCUMENT_DECLINED":
        try:
            if budget is not None:
                _reject_budget_from_decline(budget=budget, envelope_id=envelope_id)
            if workorder is not None:
                _reject_workorder_from_decline(workorder=workorder, envelope_id=envelope_id)
        except Exception:
            logger.exception(
                "signature_webhook_decline_processing_failed",
                extra={
                    "budget_id": budget.pk if budget is not None else None,
                    "workorder_id": workorder.pk if workorder is not None else None,
                    "envelope_id": envelope_id,
                },
            )
            return HttpResponse(status=500)
        return HttpResponse(status=200)

    if event_name != "ENVELOPE_COMPLETED":
        logger.info(
            "signature_webhook_event_ignored",
            extra={
                "event": event_name,
                "budget_id": budget.pk if budget is not None else None,
                "workorder_id": workorder.pk if workorder is not None else None,
            },
        )
        return HttpResponse(status=200)

    try:
        if budget is not None:
            if not budget.approve():
                budget.mark_signature_approved()
                logger.info("signature_webhook_budget_already_approved", extra={"budget_id": budget.pk, "envelope_id": envelope_id})
            else:
                logger.info("signature_webhook_budget_approved", extra={"budget_id": budget.pk, "envelope_id": envelope_id})

        if workorder is not None:
            can_finalize_workorder = workorder.is_fully_paid or workorder.budget_type in ("warranty", "courtesy")
            if can_finalize_workorder or workorder.status == WorkOrderStatus.APPROVED:
                # Garantir warranty_plan consistente antes de aprovar.
                # Apenas define default quando a finalização será efetuada;
                # WO que permanece pendente por pagamento não sofre mutação silenciosa.
                if workorder.warranty_plan is None:
                    workorder.warranty_plan = WorkOrderWarrantyPlan.DAYS_90
                    workorder.save(update_fields=["warranty_plan"])
                try:
                    approve_workorder_with_stock(workorder=workorder, signature_approved=True)
                except WorkOrderApprovalError as exc:
                    logger.warning(
                        "workorder_stock_approval_blocked",
                        extra={"workorder_id": workorder.pk, "envelope_id": envelope_id, "error": str(exc)},
                    )
                    workorder.mark_signature_approved()
                    logger.info(
                        "signature_webhook_workorder_signature_approved_pending_completion",
                        extra={
                            "workorder_id": workorder.pk,
                            "envelope_id": envelope_id,
                            "missing_warranty_plan": workorder.warranty_plan is None,
                        },
                    )
                    return HttpResponse(status=200)

                sync_workorder_financial_movement(workorder=workorder)
                from apps.messaging.application.services.satisfaction_survey import schedule_satisfaction_survey_for_workorder

                workorder.refresh_from_db()
                schedule_satisfaction_survey_for_workorder(workorder)
                logger.info("signature_webhook_workorder_approved", extra={"workorder_id": workorder.pk, "envelope_id": envelope_id})
            else:
                workorder.mark_signature_approved()
                logger.info(
                    "signature_webhook_workorder_signature_approved_pending_completion",
                    extra={
                        "workorder_id": workorder.pk,
                        "envelope_id": envelope_id,
                        "missing_warranty_plan": workorder.warranty_plan is None,
                    },
                )
    except Exception:
        logger.exception(
            "signature_webhook_processing_failed",
            extra={
                "budget_id": budget.pk if budget is not None else None,
                "workorder_id": workorder.pk if workorder is not None else None,
                "envelope_id": envelope_id,
            },
        )
        return HttpResponse(status=500)

    return HttpResponse(status=200)


@method_decorator(csrf_exempt, name="dispatch")
class SignatureWebhookView(View):
    def get(self, request: HttpRequest) -> JsonResponse:
        logger.info("signature_webhook_ping")
        return JsonResponse({"ok": True, "message": "webhook online"}, status=200)

    def post(self, request: HttpRequest) -> HttpResponse:
        from apps.workshops.services.synplaisign import get_workshop_synplaisign_webhook_secret

        logger.info("signature_webhook_received", extra={"content_type": request.content_type})

        try:
            payload = parse_signature_webhook_body(request)
        except json.JSONDecodeError:
            logger.warning("signature_webhook_invalid_json")
            return JsonResponse({"error": "invalid_json"}, status=400)

        envelope_id = _normalize_envelope_id(extract_signature_envelope_id(payload))
        workshop, budget, workorder, term_signing = (None, None, None, None)
        if envelope_id:
            workshop, budget, workorder, term_signing = _resolve_workshop_for_envelope(envelope_id)

        workshop_secret = ""
        if workshop is not None:
            workshop_secret = get_workshop_synplaisign_webhook_secret(workshop)

        validation_response = validate_signature_webhook_request(request, workshop_secret=workshop_secret)
        if validation_response is not None:
            return validation_response

        header_event = str(request.headers.get("x-synplai-event") or "").strip()
        return process_signature_webhook_payload(
            payload=payload,
            budget=budget,
            workorder=workorder,
            term_signing=term_signing,
            header_event=header_event,
        )


# Backward-compatible aliases during SuperSign → SynplaiSign cutover.
SuperSignWebhookView = SignatureWebhookView
extract_supersign_event = extract_signature_event
extract_supersign_envelope_id = extract_signature_envelope_id
validate_supersign_webhook_request = validate_signature_webhook_request
parse_supersign_webhook_body = parse_signature_webhook_body
process_supersign_webhook_payload = process_signature_webhook_payload
