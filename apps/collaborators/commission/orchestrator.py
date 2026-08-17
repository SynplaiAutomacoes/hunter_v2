from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from djmoney.money import Money

from apps.collaborators.commission.calculators import get_calculator
from apps.collaborators.commission.eligibility import CollaboratorEligibilityChecker
from apps.collaborators.models import (
    CollaboratorCommissionEntry,
    CollaboratorCommissionRule,
    CollaboratorPayroll,
    WorkshopCollaborator,
)
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshop_commission import WorkshopCommissionSettings

ZERO = Decimal("0.00")

_ORIGIN_BY_SCOPE = {
    CollaboratorCommissionRule.Scope.SERVICE: CollaboratorCommissionEntry.CommissionOrigin.SERVICE_RULE,
    CollaboratorCommissionRule.Scope.PRODUCT: CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_RULE,
}


class WorkOrderCommissionOrchestrator:
    """Ponto de entrada único para a apuração de comissões de uma WorkOrder.

    Idempotente: update-or-create por (collaborator, workorder, origin).
    Entradas ``PAID`` são imutáveis em valores econômicos (RN-12).
    """

    def __init__(self) -> None:
        self.eligibility = CollaboratorEligibilityChecker()

    def generate_commissions_for_workorder(self, *, workorder: WorkOrder, reference_date: date | None = None) -> list[CollaboratorCommissionEntry]:
        from apps.collaborators.services import (
            _resolve_commission_reference_date,
            _workorder_can_generate_commission,
            remove_pending_workorder_commissions,
        )

        with transaction.atomic():
            locked = WorkOrder.objects.select_for_update().select_related("budget", "workshop").get(pk=workorder.pk)
            if not _workorder_can_generate_commission(workorder=locked):
                remove_pending_workorder_commissions(workorder=locked)
                return []

            reference = reference_date or _resolve_commission_reference_date(workorder=locked)
            settings, _ = WorkshopCommissionSettings.objects.get_or_create(workshop=locked.workshop)

            candidates: dict[int, WorkshopCollaborator] = {}
            for collaborator in locked.collaborators.prefetch_related("commission_rules").select_related("workshop").all():
                candidates[collaborator.pk] = collaborator

            global_collaborators = (
                WorkshopCollaborator.objects.filter(
                    workshop=locked.workshop,
                    is_active=True,
                    commission_rules__is_active=True,
                    commission_rules__apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
                )
                .distinct()
                .prefetch_related("commission_rules")
                .select_related("workshop")
            )
            for collaborator in global_collaborators:
                if collaborator.pk not in candidates:
                    candidates[collaborator.pk] = collaborator

            payroll_lookup_by_collaborator: dict[int, dict[tuple[int, int], CollaboratorPayroll]] = {
                collaborator_id: {} for collaborator_id in candidates
            }
            for payroll in CollaboratorPayroll.objects.filter(collaborator_id__in=candidates).select_related("financial_movement"):
                payroll_lookup_by_collaborator.setdefault(payroll.collaborator_id, {})[(payroll.reference_year, payroll.reference_month)] = payroll

            synced: list[CollaboratorCommissionEntry] = []
            for collaborator in candidates.values():
                synced.extend(
                    self._generate_for_workorder_collaborator(
                        collaborator=collaborator,
                        workorder=locked,
                        reference=reference,
                        settings=settings,
                        existing_payroll_lookup=payroll_lookup_by_collaborator.get(collaborator.pk),
                    )
                )

            self._cleanup_stale_workorder_entries(workorder=locked, synced=synced)
            return synced

    def sync_collaborator_commissions(
        self,
        *,
        collaborator: WorkshopCollaborator,
        reference_date: date | None = None,
        lock_reference: bool = False,
    ) -> list[CollaboratorCommissionEntry]:
        """Camada de compatibilidade: apura as comissões de um collaborator (mês alvo)."""
        from apps.collaborators.services import (
            _resolve_commission_reference_date,
            _resolve_payroll_reference_date_from_lookup,
            _resolve_reference_date,
            _workorder_can_generate_commission,
            remove_pending_workorder_commissions,
        )

        resolved = _resolve_reference_date(reference_date)
        settings, _ = WorkshopCommissionSettings.objects.get_or_create(workshop=collaborator.workshop)
        effective_rules = self.eligibility.get_effective_rules(collaborator=collaborator)

        participation_ids = set(
            WorkOrder.objects.filter(workshop=collaborator.workshop, collaborators=collaborator).values_list("id", flat=True)
        )
        workorder_ids = set(participation_ids)
        for rule in effective_rules:
            if rule.apply_scope == CollaboratorCommissionRule.ApplyScope.GLOBAL:
                workorder_ids |= set(
                    WorkOrder.objects.filter(
                        workshop=collaborator.workshop,
                        budget_type="sale",
                        status=WorkOrderStatus.APPROVED,
                    ).values_list("id", flat=True)
                )

        workorders = list(
            WorkOrder.objects.filter(pk__in=workorder_ids)
            .select_related("budget")
            .prefetch_related("payments", self._workorder_items_prefetch())
            .order_by("id")
        )

        existing_payroll_lookup = {
            (payroll.reference_year, payroll.reference_month): payroll
            for payroll in CollaboratorPayroll.objects.filter(collaborator=collaborator).select_related("financial_movement")
        }

        synced: list[CollaboratorCommissionEntry] = []
        protected_workorder_ids: set[int] = set()
        for workorder in workorders:
            if not _workorder_can_generate_commission(workorder=workorder):
                remove_pending_workorder_commissions(workorder=workorder)
                continue
            protected_workorder_ids.add(workorder.pk)

            commission_reference = _resolve_commission_reference_date(workorder=workorder)
            effective_reference = _resolve_payroll_reference_date_from_lookup(
                collaborator=collaborator,
                reference_date=commission_reference,
                lock_reference=lock_reference,
                existing_payroll_lookup=existing_payroll_lookup,
            )
            if effective_reference.year != resolved.year or effective_reference.month != resolved.month:
                continue

            synced.extend(
                self._generate_for_workorder_collaborator(
                    collaborator=collaborator,
                    workorder=workorder,
                    effective_reference=effective_reference,
                    settings=settings,
                    existing_payroll_lookup=existing_payroll_lookup,
                )
            )

        stale_entries = CollaboratorCommissionEntry.objects.filter(
            collaborator=collaborator,
            reference_year=resolved.year,
            reference_month=resolved.month,
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )
        if protected_workorder_ids:
            stale_entries = stale_entries.exclude(workorder_id__in=protected_workorder_ids)
        stale_entries.delete()
        return synced

    def _generate_for_workorder_collaborator(
        self,
        *,
        collaborator: WorkshopCollaborator,
        workorder: WorkOrder,
        settings,
        reference: date | None = None,
        effective_reference: date | None = None,
        existing_payroll_lookup: dict[tuple[int, int], CollaboratorPayroll] | None = None,
        lock_reference: bool = False,
    ) -> list[CollaboratorCommissionEntry]:
        synced: list[CollaboratorCommissionEntry] = []

        for rule in self.eligibility.get_eligible_rules_for_workorder(collaborator=collaborator, workorder=workorder):
            origin = _ORIGIN_BY_SCOPE[rule.scope]
            entry = self._upsert_entry(
                collaborator=collaborator,
                workorder=workorder,
                origin=origin,
                rule=rule,
                reference=reference,
                effective_reference=effective_reference,
                existing_payroll_lookup=existing_payroll_lookup,
                lock_reference=lock_reference,
            )
            if entry is not None:
                synced.append(entry)

        if self.eligibility.is_eligible_for_workorder_rate(collaborator=collaborator, workorder=workorder, settings=settings):
            entry = self._upsert_entry(
                collaborator=collaborator,
                workorder=workorder,
                origin=CollaboratorCommissionEntry.CommissionOrigin.WORKORDER_RATE,
                rule=None,
                percentage=settings.workorder_commission_percentage,
                reference=reference,
                effective_reference=effective_reference,
                existing_payroll_lookup=existing_payroll_lookup,
                lock_reference=lock_reference,
            )
            if entry is not None:
                synced.append(entry)

        return synced

    def _upsert_entry(
        self,
        *,
        collaborator: WorkshopCollaborator,
        workorder: WorkOrder,
        origin: str,
        rule: CollaboratorCommissionRule | None = None,
        percentage: Decimal | None = None,
        fixed_amount: Decimal | None = None,
        reference: date | None = None,
        effective_reference: date | None = None,
        existing_payroll_lookup: dict[tuple[int, int], CollaboratorPayroll] | None = None,
        lock_reference: bool = False,
    ) -> CollaboratorCommissionEntry | None:
        from apps.collaborators.services import _resolve_payroll_reference_date_from_lookup

        if effective_reference is None:
            if reference is None:
                return None
            effective_reference = _resolve_payroll_reference_date_from_lookup(
                collaborator=collaborator,
                reference_date=reference,
                lock_reference=lock_reference,
                existing_payroll_lookup=existing_payroll_lookup,
            )

        calculator = get_calculator(rule=rule, for_workorder_rate=(origin == CollaboratorCommissionEntry.CommissionOrigin.WORKORDER_RATE))
        base = calculator.calculate_base(workorder=workorder)
        commission = calculator.calculate_commission(base=base, rule=rule, percentage=percentage, fixed_amount=fixed_amount)
        is_fixed = bool(rule.is_fixed_amount) if rule is not None else fixed_amount is not None
        rule_id = rule.pk if rule is not None and rule.pk else None
        if is_fixed:
            stored_percentage = rule.resolved_percentage if rule is not None else ZERO
        elif rule is not None:
            stored_percentage = rule.resolved_percentage
        else:
            stored_percentage = percentage or ZERO
        resolved_percentage = Decimal(str(stored_percentage or ZERO))

        entry, created = CollaboratorCommissionEntry.objects.get_or_create(
            workshop=collaborator.workshop,
            collaborator=collaborator,
            workorder=workorder,
            commission_origin=origin,
            defaults={
                "reference_year": effective_reference.year,
                "reference_month": effective_reference.month,
                "percentage": resolved_percentage,
                "base_amount": Money(base, "BRL"),
                "commission_amount": Money(commission, "BRL"),
                "commission_rule_id": rule_id,
                "is_fixed_amount": is_fixed,
                "status": CollaboratorCommissionEntry.Status.FORECAST,
            },
        )

        if not created:
            if entry.status == CollaboratorCommissionEntry.Status.PAID:
                update_fields: list[str] = []
                if entry.workshop_id != collaborator.workshop_id:
                    entry.workshop = collaborator.workshop
                    update_fields.append("workshop")
                if entry.reference_year != effective_reference.year:
                    entry.reference_year = effective_reference.year
                    update_fields.append("reference_year")
                if entry.reference_month != effective_reference.month:
                    entry.reference_month = effective_reference.month
                    update_fields.append("reference_month")
                if entry.percentage != resolved_percentage:
                    entry.percentage = resolved_percentage
                    update_fields.append("percentage")
                if update_fields:
                    entry.save(update_fields=update_fields)
            else:
                entry.workshop = collaborator.workshop
                entry.reference_year = effective_reference.year
                entry.reference_month = effective_reference.month
                entry.percentage = resolved_percentage
                entry.base_amount = Money(base, "BRL")
                entry.commission_amount = Money(commission, "BRL")
                entry.commission_rule_id = rule_id
                entry.is_fixed_amount = is_fixed
                entry.status = CollaboratorCommissionEntry.Status.FORECAST
                entry.paid_at = None
                entry.save(
                    update_fields=[
                        "workshop",
                        "reference_year",
                        "reference_month",
                        "percentage",
                        "base_amount",
                        "commission_amount",
                        "commission_rule",
                        "is_fixed_amount",
                        "status",
                        "paid_at",
                    ]
                )
        return entry

    def _cleanup_stale_workorder_entries(self, *, workorder: WorkOrder, synced: list[CollaboratorCommissionEntry]) -> None:
        synced_ids = {entry.pk for entry in synced if entry.pk}
        stale_entries = CollaboratorCommissionEntry.objects.filter(
            workorder=workorder,
            status=CollaboratorCommissionEntry.Status.FORECAST,
        ).exclude(pk__in=synced_ids)
        stale_entries.delete()

    @staticmethod
    def _workorder_items_prefetch():
        from apps.core.infrastructure.kit_prefetch import workorder_items_with_kit_prefetch

        return workorder_items_with_kit_prefetch(with_kit_tree=True)