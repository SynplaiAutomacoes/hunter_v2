from __future__ import annotations

from apps.terms.models import BudgetTermSigning, TermTemplateType, WorkOrderTermSigning, WorkshopTermTemplate


def get_active_term_templates(*, workshop, template_type: str) -> list[WorkshopTermTemplate]:
    return list(
        WorkshopTermTemplate.objects.filter(
            workshop=workshop,
            template_type=template_type,
            is_active=True,
        ).order_by("-is_default", "name")
    )


def get_default_term_template(*, workshop, template_type: str) -> WorkshopTermTemplate | None:
    return (
        WorkshopTermTemplate.objects.filter(
            workshop=workshop,
            template_type=template_type,
            is_active=True,
        )
        .order_by("-is_default", "id")
        .first()
    )


def get_or_create_budget_term_signing(*, budget, term_template: WorkshopTermTemplate | None = None) -> BudgetTermSigning:
    existing = BudgetTermSigning.objects.filter(budget=budget).select_related("term_template").first()
    if existing is not None:
        return existing

    resolved_template = term_template or get_default_term_template(
        workshop=budget.workshop,
        template_type=TermTemplateType.VEHICLE_RECEIPT,
    )
    if resolved_template is None:
        raise ValueError("Nenhum termo de recebimento ativo cadastrado para esta oficina.")

    return BudgetTermSigning.objects.create(budget=budget, term_template=resolved_template)


def update_budget_term_template(*, budget, term_template_id: int | None) -> BudgetTermSigning | None:
    if term_template_id is None:
        return BudgetTermSigning.objects.filter(budget=budget).select_related("term_template").first()

    term_template = WorkshopTermTemplate.objects.filter(
        pk=term_template_id,
        workshop=budget.workshop,
        template_type=TermTemplateType.VEHICLE_RECEIPT,
        is_active=True,
    ).first()
    if term_template is None:
        raise ValueError("Termo selecionado inválido ou inativo.")

    signing, _created = BudgetTermSigning.objects.get_or_create(
        budget=budget,
        defaults={"term_template": term_template},
    )
    if signing.is_signature_locked:
        return signing

    if signing.term_template_id != term_template.pk:
        signing.term_template = term_template
        signing.save(update_fields=["term_template", "atualizado_em"])
    return signing


def update_workorder_term_template(*, workorder, term_template_id: int | None) -> WorkOrderTermSigning | None:
    if term_template_id is None:
        return WorkOrderTermSigning.objects.filter(workorder=workorder).select_related("term_template").first()

    term_template = WorkshopTermTemplate.objects.filter(
        pk=term_template_id,
        workshop=workorder.workshop,
        template_type=TermTemplateType.WARRANTY,
        is_active=True,
    ).first()
    if term_template is None:
        raise ValueError("Termo de garantia selecionado inválido ou inativo.")

    signing, _created = WorkOrderTermSigning.objects.get_or_create(
        workorder=workorder,
        defaults={"term_template": term_template},
    )
    if signing.is_signature_locked:
        return signing

    if signing.term_template_id != term_template.pk:
        signing.term_template = term_template
        signing.save(update_fields=["term_template", "atualizado_em"])
    return signing
