from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorCommissionRule, WorkOrderCommissionAllocation
from apps.workorder.models import WorkOrder


def participation_pct_collaborator_ids(*, workorder: WorkOrder, scope: str) -> set[int]:
    wo_collaborator_ids = set(workorder.collaborators.values_list("id", flat=True))
    if not wo_collaborator_ids:
        return set()
    return set(
        CollaboratorCommissionRule.objects.filter(
            collaborator_id__in=wo_collaborator_ids,
            scope=scope,
            is_active=True,
            modality=CollaboratorCommissionRule.Modality.PERCENTAGE,
            apply_scope=CollaboratorCommissionRule.ApplyScope.PARTICIPATION,
        ).values_list("collaborator_id", flat=True)
    )


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
    @transaction.atomic
    def sync_for_workorder(*, workorder: WorkOrder) -> None:
        """Remove alocações órfãs e aplica Base 100% quando há um único elegível por escopo."""
        if CollaboratorCommissionEntry.objects.filter(
            workorder=workorder,
            status=CollaboratorCommissionEntry.Status.PAID,
        ).exists():
            return

        locked_workorder = WorkOrder.objects.select_for_update().get(pk=workorder.pk)
        wo_collaborator_ids = set(locked_workorder.collaborators.values_list("id", flat=True))

        orphan_qs = WorkOrderCommissionAllocation.objects.filter(workorder=locked_workorder).exclude(
            collaborator_id__in=wo_collaborator_ids
        )
        scopes_with_removed_allocations = set(orphan_qs.values_list("scope", flat=True).distinct())
        orphan_qs.delete()

        for scope in (CollaboratorCommissionRule.Scope.SERVICE, CollaboratorCommissionRule.Scope.PRODUCT):
            eligible_ids = participation_pct_collaborator_ids(workorder=locked_workorder, scope=scope)
            WorkOrderCommissionAllocation.objects.filter(
                workorder=locked_workorder,
                scope=scope,
            ).exclude(collaborator_id__in=eligible_ids).delete()

            eligible_collaborators = list(locked_workorder.collaborators.filter(id__in=eligible_ids).order_by("id"))
            if len(eligible_collaborators) != 1:
                continue

            sole = eligible_collaborators[0]
            sole_allocation = WorkOrderCommissionAllocation.objects.filter(
                workorder=locked_workorder,
                scope=scope,
                collaborator=sole,
            ).first()
            if sole_allocation is None or scope in scopes_with_removed_allocations:
                CommissionAllocationService.upsert(
                    workorder=locked_workorder,
                    collaborator=sole,
                    scope=scope,
                    distribution_percentage=Decimal("1"),
                )

    @staticmethod
    def validate(*, workorder: WorkOrder, scope: str) -> dict[str, list[str]]:
        """Valida soma das Bases ≤100% (apenas alertas)."""
        errors: dict[str, list[str]] = {"cap": [], "sum": []}
        eligible_ids = participation_pct_collaborator_ids(workorder=workorder, scope=scope)
        if not eligible_ids:
            return errors

        allocations = list(
            WorkOrderCommissionAllocation.objects.filter(
                workorder=workorder,
                scope=scope,
                collaborator_id__in=eligible_ids,
            )
        )
        if not allocations:
            return errors

        sum_pct = sum((Decimal(str(alloc.distribution_percentage or 0)) for alloc in allocations), Decimal("0"))
        if sum_pct > Decimal("1"):
            sum_display = (sum_pct * Decimal("100")).quantize(Decimal("0.01"))
            errors["sum"].append(f"Soma das Bases ({sum_display}%) ultrapassa 100%.")

        return errors
