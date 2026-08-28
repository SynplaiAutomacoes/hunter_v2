from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.collaborators.models import CollaboratorCommissionRule, WorkOrderCommissionAllocation
from apps.workorder.models import WorkOrder


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CommissionAllocationService:
    """Gerencia Base (%) por WO — alocação do pool."""

    @staticmethod
    @transaction.atomic
    def upsert(*, workorder: WorkOrder, collaborator, scope: str, distribution_percentage) -> WorkOrderCommissionAllocation:
        pct = Decimal(str(distribution_percentage or 0))
        if pct < 0 or pct > 1:
            raise ValidationError("Base (%) deve estar entre 0 e 100%.")
        # Regra deve existir, ser % e participation
        rule_exists = CollaboratorCommissionRule.objects.filter(
            collaborator=collaborator,
            scope=scope,
            is_active=True,
            modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
            apply_scope=CollaboratorCommissionRule.ApplyScope.PARTICIPATION,
        ).exists()
        # Permite alocação mesmo sem regra? Mas bloqueia se não for P_pct
        # Para evitar erro silencioso, validar — porém permitir 0
        if not rule_exists and pct > 0:
            raise ValidationError("Colaborador não possui regra de percentual por participação neste escopo.")

        allocation, _ = WorkOrderCommissionAllocation.objects.select_for_update().get_or_create(
            workorder=workorder,
            collaborator=collaborator,
            scope=scope,
            defaults={"distribution_percentage": pct},
        )
        if allocation.distribution_percentage != pct:
            allocation.distribution_percentage = pct
            allocation.save(update_fields=["distribution_percentage"])
        return allocation

    @staticmethod
    def validate(*, workorder: WorkOrder, scope: str) -> dict[str, list[str]]:
        """Valida caps individuais e soma ≤100% (apenas alertas)."""
        errors: dict[str, list[str]] = {"cap": [], "sum": []}
        allocations = list(WorkOrderCommissionAllocation.objects.filter(workorder=workorder, scope=scope).select_related("collaborator"))
        if not allocations:
            return errors

        # Calcular max_pct_S a partir de TODOS os participantes da WO (não só dos já alocados) — fix 4.1
        from apps.collaborators.models import CollaboratorCommissionRule

        # Todos os colaboradores vinculados à WO para este escopo
        wo_collaborator_ids = list(workorder.collaborators.values_list("id", flat=True))
        # Regras de percentual por participação de todos os participantes
        all_participant_rules = {
            r.collaborator_id: r
            for r in CollaboratorCommissionRule.objects.filter(
                collaborator_id__in=wo_collaborator_ids,
                scope=scope,
                is_active=True,
                modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
                apply_scope=CollaboratorCommissionRule.ApplyScope.PARTICIPATION,
            )
        }
        # Para validação individual, precisamos do mapa de allocated → rule (pode ser subconjunto)
        collaborator_ids = [a.collaborator_id for a in allocations]
        rules = {
            cid: rule for cid, rule in all_participant_rules.items() if cid in collaborator_ids
        }
        # Considerar apenas colaboradores que estão na WO
        workshop = workorder.workshop
        # max_pct_S deve considerar todos os participantes, não só alocados (evita cap 100% falso quando só Maria alocada)
        max_pct = Decimal("0")
        for rule in all_participant_rules.values():
            pct = Decimal(str(rule.percentage or 0))
            if pct > max_pct:
                max_pct = pct
        if max_pct <= 0:
            return errors

        sum_pct = Decimal("0")
        for alloc in allocations:
            dist = Decimal(str(alloc.distribution_percentage or 0))
            sum_pct += dist
            rule = rules.get(alloc.collaborator_id)
            if rule is None:
                continue
            cap = (Decimal(str(rule.percentage or 0)) / max_pct) if max_pct > 0 else Decimal("1")
            if dist > cap:
                cap_display = (cap * Decimal("100")).quantize(Decimal("0.01"))
                errors["cap"].append(
                    f"{alloc.collaborator.name}: Base { (dist*Decimal('100')).quantize(Decimal('0.01')) }% ultrapassa o máximo permitido {cap_display}%."
                )
        if sum_pct > Decimal("1"):
            sum_display = (sum_pct * Decimal("100")).quantize(Decimal("0.01"))
            errors["sum"].append(f"Soma das Bases ({sum_display}%) ultrapassa 100%.")

        return errors
