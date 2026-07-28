from __future__ import annotations

import logging

from apps.messaging.models import MessageTemplate

logger = logging.getLogger(__name__)


def get_active_template(workshop_id: int, template_type: str) -> MessageTemplate | None:
    if template_type == MessageTemplate.TemplateType.GENERIC:
        return None

    return (
        MessageTemplate.objects.filter(
            workshop_id=workshop_id,
            template_type=template_type,
            is_active=True,
        )
        .order_by("-atualizado_em", "-pk")
        .first()
    )


def deactivate_other_active_typed_templates(*, workshop_id: int, template_type: str, keep_pk: int | None = None) -> int:
    if template_type not in MessageTemplate.SPECIAL_TYPES:
        return 0

    queryset = MessageTemplate.objects.filter(
        workshop_id=workshop_id,
        template_type=template_type,
        is_active=True,
    )
    if keep_pk is not None:
        queryset = queryset.exclude(pk=keep_pk)
    return queryset.update(is_active=False)
