from __future__ import annotations

import logging
import uuid

from django.conf import settings

from apps.core.domain.contracts.documents import normalize_signature_phone_number
from apps.messaging.application.services.dispatch_history import (
    create_dispatch_batch,
    finalize_batch_after_queue,
    record_queue_failure,
    record_queued_log,
)
from apps.messaging.domain.value_objects import DispatchItem
from apps.messaging.infrastructure.queue.rabbitmq_publisher import RabbitMQPublisher, RabbitMQPublisherError
from apps.messaging.models import MessageDispatchBatch


logger = logging.getLogger(__name__)


def maybe_dispatch_signature_whatsapp(
    *,
    workshop,
    customer,
    phone: object,
    document_title: str,
    signing_url: str,
) -> bool:
    """Queue WhatsApp delivery of the signing link via the workshop Evolution instance.

    Returns True when a message was queued. Failures are logged and never raised —
    SynplaiSign email remains the delivery fallback after envelope send.
    """
    signing_url = str(signing_url or "").strip()
    if not signing_url:
        return False

    instance_name = str(getattr(workshop, "whatsapp_instance_name", "") or "").strip()
    if not instance_name:
        logger.info(
            "signature_whatsapp_skipped_no_instance",
            extra={"workshop_id": getattr(workshop, "pk", None)},
        )
        return False

    region = getattr(settings, "PHONENUMBER_DEFAULT_REGION", "BR")
    normalized_phone = normalize_signature_phone_number(phone, default_region=region)
    if not normalized_phone:
        logger.info(
            "signature_whatsapp_skipped_no_phone",
            extra={"workshop_id": getattr(workshop, "pk", None)},
        )
        return False

    # Worker expects digits without leading '+'.
    phone_digits = normalized_phone.lstrip("+")
    customer_id = int(getattr(customer, "pk", 0) or 0)
    workshop_id = int(getattr(workshop, "pk", 0) or 0)
    if workshop_id <= 0:
        return False

    message = (
        f"Olá! Segue o documento *{document_title}* para assinatura digital.\n\n"
        f"Acesse o link para assinar:\n{signing_url}"
    )
    client_message_id = uuid.uuid4()
    batch = create_dispatch_batch(
        workshop_id=workshop_id,
        source=MessageDispatchBatch.Source.COMMAND,
    )
    item = DispatchItem(
        group_id=None,
        workshop_id=workshop_id,
        customer_id=customer_id,
        phone=phone_digits,
        message=message,
        client_message_id=str(client_message_id),
        batch_id=batch.pk,
    )

    publisher = RabbitMQPublisher(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        username=settings.RABBITMQ_USER,
        password=settings.RABBITMQ_PASSWORD,
    )
    try:
        publisher.publish_dispatch_item(item, workshop_id=workshop_id)
        record_queued_log(
            batch=batch,
            client_message_id=client_message_id,
            customer_id=customer_id or None,
            phone=phone_digits,
            message=message,
        )
        finalize_batch_after_queue(batch)
        publisher.publish_workshop_control(workshop_id, whatsapp_instance_name=instance_name)
        logger.info(
            "signature_whatsapp_queued",
            extra={
                "workshop_id": workshop_id,
                "customer_id": customer_id or None,
                "batch_id": batch.pk,
                "instance_name": instance_name,
            },
        )
        return True
    except (RabbitMQPublisherError, Exception) as exc:
        logger.exception(
            "signature_whatsapp_queue_failed",
            extra={"workshop_id": workshop_id, "batch_id": batch.pk, "error": str(exc)},
        )
        record_queue_failure(
            batch=batch,
            client_message_id=client_message_id,
            customer_id=customer_id or None,
            phone=phone_digits,
            message=message,
            error=str(exc),
        )
        finalize_batch_after_queue(batch)
        return False
    finally:
        publisher.close()
