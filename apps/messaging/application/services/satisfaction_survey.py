from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.customer.services.messaging_consent import customer_can_receive_messages
from apps.messaging.application.services.typed_templates import get_active_template
from apps.messaging.models import MessageTemplate, SatisfactionReview, ScheduledOutboundMessage
from apps.messaging.rendering import render_message_template
from apps.workorder.models import WorkOrder

logger = logging.getLogger(__name__)


def allows_immediate_satisfaction_survey() -> bool:
    environment = str(getattr(settings, "ENVIRONMENT", "") or "").strip().lower().strip('"').strip("'")
    return environment not in {"prod", "production"}


def resolve_satisfaction_survey_run_at(
    *,
    delay_days: int,
    delivered_at: datetime,
    send_immediately: bool = False,
) -> datetime:
    if send_immediately and allows_immediate_satisfaction_survey():
        return timezone.now()
    if send_immediately and not allows_immediate_satisfaction_survey():
        logger.warning("satisfaction_survey_immediate_ignored_in_production")
    safe_delay = max(0, int(delay_days))
    return delivered_at + timedelta(days=safe_delay)


def build_satisfaction_review_url(public_token: str) -> str:
    base = str(getattr(settings, "APP_BASE_URL", "") or "").rstrip("/")
    return f"{base}/review/{public_token}"


def resolve_workorder_customer_phone(workorder: WorkOrder) -> str:
    customer = getattr(getattr(workorder, "budget", None), "customer", None)
    if customer is None:
        return ""
    phone = getattr(customer, "phone", None)
    if phone is None:
        return ""
    as_e164 = getattr(phone, "as_e164", None)
    if not as_e164:
        return ""
    return str(as_e164).lstrip("+")


def build_satisfaction_survey_message(*, workorder: WorkOrder, public_token: str) -> str | None:
    template = get_active_template(workorder.workshop_id, MessageTemplate.TemplateType.SATISFACTION)
    if template is None:
        logger.info(
            "satisfaction_survey_skipped_no_active_template",
            extra={"workshop_id": workorder.workshop_id, "workorder_id": workorder.pk},
        )
        return None

    customer = workorder.budget.customer
    workshop = workorder.workshop
    return render_message_template(
        template.message,
        customer=customer,
        workshop=workshop,
        workorder=workorder,
        extras={"link-avaliacao": build_satisfaction_review_url(public_token)},
    )


@transaction.atomic
def schedule_satisfaction_survey_for_workorder(workorder: WorkOrder) -> SatisfactionReview | None:
    workshop = workorder.workshop
    if not getattr(workshop, "satisfaction_survey_enabled", False):
        return None

    if SatisfactionReview.objects.filter(workorder=workorder).exists():
        return SatisfactionReview.objects.filter(workorder=workorder).first()

    customer = getattr(getattr(workorder, "budget", None), "customer", None)
    if customer is None:
        logger.info("satisfaction_survey_skipped_no_customer", extra={"workorder_id": workorder.pk})
        return None

    if not customer_can_receive_messages(customer):
        logger.info("satisfaction_survey_skipped_customer_opted_out", extra={"workorder_id": workorder.pk, "customer_id": customer.pk})
        return None

    phone = resolve_workorder_customer_phone(workorder)
    if not phone:
        logger.info("satisfaction_survey_skipped_no_phone", extra={"workorder_id": workorder.pk, "customer_id": customer.pk})
        return None

    raw_delay = getattr(workshop, "satisfaction_survey_delay_days", 1)
    delay_days = 1 if raw_delay is None else int(raw_delay)
    send_immediately = bool(getattr(workshop, "satisfaction_survey_send_immediately", False))
    delivered_at = workorder.delivered_at or timezone.now()
    run_at = resolve_satisfaction_survey_run_at(
        delay_days=delay_days,
        delivered_at=delivered_at,
        send_immediately=send_immediately,
    )

    review = SatisfactionReview.objects.create(
        workshop=workshop,
        customer=customer,
        workorder=workorder,
        status=SatisfactionReview.Status.PENDING,
    )
    message = build_satisfaction_survey_message(workorder=workorder, public_token=review.public_token)
    if not message:
        review.status = SatisfactionReview.Status.CANCELLED
        review.save(update_fields=["status", "atualizado_em"])
        return None

    scheduled = ScheduledOutboundMessage.objects.create(
        workshop_id=workshop.pk,
        customer_id=customer.pk,
        phone=phone,
        message=message,
        run_at=run_at,
        status=ScheduledOutboundMessage.Status.PENDING,
        source=ScheduledOutboundMessage.Source.SATISFACTION_SURVEY,
    )
    review.scheduled_message = scheduled
    review.save(update_fields=["scheduled_message", "atualizado_em"])
    logger.info(
        "satisfaction_survey_scheduled",
        extra={"workorder_id": workorder.pk, "review_id": review.pk, "run_at": run_at.isoformat()},
    )
    return review


def mark_satisfaction_review_sent(scheduled: ScheduledOutboundMessage) -> None:
    if scheduled.source != ScheduledOutboundMessage.Source.SATISFACTION_SURVEY:
        return
    review = SatisfactionReview.objects.filter(scheduled_message=scheduled).first()
    if review is None or review.status != SatisfactionReview.Status.PENDING:
        return
    review.status = SatisfactionReview.Status.SENT
    review.sent_at = timezone.now()
    review.save(update_fields=["status", "sent_at", "atualizado_em"])
