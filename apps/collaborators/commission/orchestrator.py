from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.db import transaction
from django.utils import timezone
from djmoney.money import Money

from apps.collaborators.commission.calculators import calculate_total_for_scope
from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorCommissionRule, WorkOrderCommissionAllocation, WorkshopCollaborator
from apps.workorder.models import WorkOrder, WorkOrderStatus

ZERO = Decimal("0.00")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Money:
    return Money(_quantize(value), "BRL")


def _resolve_commission_reference_date(workorder: WorkOrder) -> date:
    latest_due = None
    try:
        payments = list(workorder.payments.all()) if hasattr(workorder, "payments") else []
        latest_due = max((p.due_date for p in payments if getattr(p, "due_date", None)), default=None)
    except Exception:
        latest_due = None
    if latest_due is not None:
        return date(latest_due.year, latest_due.month, 1)
    created_at = getattr(workorder, "criado_em", None)
    if created_at is not None:
        try:
            d = created_at.date() if hasattr(created_at, "date") else timezone.localdate()
            return date(d.year, d.month, 1)
        except Exception:
            pass
    return date(timezone.localdate().year, timezone.localdate().month, 1)


def _workorder_can_generate_commission(workorder: WorkOrder) -> bool:
    budget_type = getattr(workorder, "budget_type", "") or (getattr(workorder.budget, "budget_type", "") if getattr(workorder, "budget", None) else "")
    return str(workorder.status) == WorkOrderStatus.APPROVED and str(budget_type).lower() == "sale"


ORIGIN_MAP = {
    ("service", "pct_pool"): CollaboratorCommissionEntry.CommissionOrigin.SERVICE_PCT_POOL,
    ("service", "fixed"): CollaboratorCommissionEntry.CommissionOrigin.SERVICE_FIXED,
    ("product", "pct_pool"): CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_PCT_POOL,
    ("product", "fixed"): CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_FIXED,
    ("service", "global"): CollaboratorCommissionEntry.CommissionOrigin.SERVICE_GLOBAL,
    ("product", "global"): CollaboratorCommissionEntry.CommissionOrigin.PRODUCT_GLOBAL,
}


class WorkOrderCommissionOrchestrator:
    """Orquestrador pool + global + fixed (v3). Idempotente e respeita PAID imutável."""

    def generate_commissions_for_workorder(self, workorder: WorkOrder, reference_date: date | None = None) -> list[CollaboratorCommissionEntry]:
        # Lock workorder to avoid race
        with transaction.atomic():
            locked = WorkOrder.objects.select_for_update().select_related("workshop", "budget").get(pk=workorder.pk)
            # Prefetch needed relations for calculators and collaborator checks
            # need items for calculators: ensure _iter_items works; no extra prefetch required
            # but fetch collaborators
            collabs = list(locked.collaborators.all().prefetch_related("commission_rules"))
            # Also need workorder payments for reference date
            # Force fetch payments if not prefetched
            if not hasattr(locked, "_prefetched_objects_cache") or "payments" not in locked._prefetched_objects_cache:
                list(locked.payments.all())

            if not _workorder_can_generate_commission(locked):
                # Remove pending FORECAST for this workorder
                CollaboratorCommissionEntry.objects.filter(workorder=locked, status=CollaboratorCommissionEntry.Status.FORECAST).delete()
                return []

            workshop = locked.workshop
            reference = reference_date or _resolve_commission_reference_date(locked)

            # Allocations por escopo (strict: lock para evitar corrida)
            allocations_by_scope: dict[str, dict[int, WorkOrderCommissionAllocation]] = {"service": {}, "product": {}}
            for alloc in WorkOrderCommissionAllocation.objects.select_for_update().filter(workorder=locked).select_related("collaborator"):
                allocations_by_scope.setdefault(alloc.scope, {})[alloc.collaborator_id] = alloc

            synced: list[CollaboratorCommissionEntry] = []
            # Process each scope
            for scope in ("service", "product"):
                total_S = calculate_total_for_scope(workorder=locked, workshop=workshop, scope=scope)
                total_S_money = _money(total_S)
                # Segregar candidatos
                # P_fix / P_pct: ativos, participação, colaborador ∈ WO
                collab_ids_in_wo = {c.pk for c in collabs}
                rules_in_wo = CollaboratorCommissionRule.objects.filter(
                    collaborator_id__in=collab_ids_in_wo,
                    scope=scope,
                    is_active=True,
                ).select_related("collaborator")

                P_fix = [r for r in rules_in_wo if r.modality == CollaboratorCommissionRule.Modality.FIXED and r.apply_scope == CollaboratorCommissionRule.ApplyScope.PARTICIPATION]
                P_pct = [r for r in rules_in_wo if r.modality == CollaboratorCommissionRule.Modality.PERCENTAGE and r.apply_scope == CollaboratorCommissionRule.ApplyScope.PARTICIPATION]

                # G: global, workshop-wide, is_active, collaborator.is_active, criado_em <= workorder.criado_em
                G = list(
                    CollaboratorCommissionRule.objects.filter(
                        scope=scope,
                        is_active=True,
                        apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
                        collaborator__workshop=workshop,
                        collaborator__is_active=True,
                        criado_em__lte=locked.criado_em,
                    ).select_related("collaborator")
                )

                max_pct_S = Decimal("0")
                for r in P_pct:
                    pct = Decimal(str(r.percentage or 0))
                    if pct > max_pct_S:
                        max_pct_S = pct
                pool_S = _quantize(total_S * max_pct_S) if max_pct_S > 0 else ZERO
                pool_S_money = _money(pool_S)

                # Para Fixed (participação)
                for rule in P_fix:
                    commission_amount = _quantize(Decimal(str(getattr(rule.fixed_amount, "amount", 0) or 0)))
                    origin = ORIGIN_MAP[(scope, "fixed")]
                    entry = self._upsert_entry(
                        collaborator=rule.collaborator,
                        workorder=locked,
                        workshop=workshop,
                        origin=origin,
                        rule=rule,
                        base_amount=total_S_money,
                        pool_amount=pool_S_money,
                        distribution_pct=ZERO,
                        commission_amount=_money(commission_amount),
                        reference=reference,
                        is_fixed=True,
                    )
                    if entry:
                        synced.append(entry)

                # Para Pct Pool (participação)
                for rule in P_pct:
                    alloc = allocations_by_scope.get(scope, {}).get(rule.collaborator_id)
                    dist_pct = Decimal(str(alloc.distribution_percentage or 0)) if alloc else ZERO
                    commission_amount = _quantize(pool_S * dist_pct)
                    origin = ORIGIN_MAP[(scope, "pct_pool")]
                    entry = self._upsert_entry(
                        collaborator=rule.collaborator,
                        workorder=locked,
                        workshop=workshop,
                        origin=origin,
                        rule=rule,
                        base_amount=total_S_money,
                        pool_amount=pool_S_money,
                        distribution_pct=dist_pct,
                        commission_amount=_money(commission_amount),
                        reference=reference,
                        is_fixed=False,
                    )
                    if entry:
                        synced.append(entry)

                # Para Global (fora do pool)
                for rule in G:
                    if rule.modality == CollaboratorCommissionRule.Modality.FIXED:
                        commission_amount = _quantize(Decimal(str(getattr(rule.fixed_amount, "amount", 0) or 0)))
                        is_fixed = True
                    else:
                        commission_amount = _quantize(total_S * Decimal(str(rule.percentage or 0)))
                        is_fixed = False
                    origin = ORIGIN_MAP[(scope, "global")]
                    entry = self._upsert_entry(
                        collaborator=rule.collaborator,
                        workorder=locked,
                        workshop=workshop,
                        origin=origin,
                        rule=rule,
                        base_amount=total_S_money,
                        pool_amount=pool_S_money,
                        distribution_pct=ZERO,
                        commission_amount=_money(commission_amount),
                        reference=reference,
                        is_fixed=is_fixed,
                    )
                    if entry:
                        synced.append(entry)

            # Limpeza de stale FORECAST (remover entradas que não foram geradas nesta execução mas existem como FORECAST)
            synced_ids = {e.pk for e in synced if e.pk}
            stale_qs = CollaboratorCommissionEntry.objects.filter(workorder=locked, status=CollaboratorCommissionEntry.Status.FORECAST)
            if synced_ids:
                stale_qs = stale_qs.exclude(pk__in=synced_ids)
            stale_qs.delete()

            return synced

    def sync_collaborator_commissions(self, collaborator: WorkshopCollaborator, reference_date: date | None = None, lock_reference: bool = False) -> list[CollaboratorCommissionEntry]:
        """Compatibilidade: apura comissões de todas as WOs relevantes ao colaborador (mês alvo)."""
        from apps.collaborators.services import _resolve_payroll_reference_date_from_lookup, _resolve_reference_date

        resolved = _resolve_reference_date(reference_date)
        # Workorders que podem gerar comissão para este colaborador (participação ou global)
        # Participação: WO onde collaborator ∈ workorder.collaborators
        participation_ids = set(WorkOrder.objects.filter(workshop=collaborator.workshop, collaborators=collaborator).values_list("id", flat=True))
        # Global: todas as WOs de venda aprovadas criadas após a regra global do colaborador
        # Se não tem regra global, não precisa adicionar
        has_global = CollaboratorCommissionRule.objects.filter(
            collaborator=collaborator, apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL, is_active=True
        ).exists()
        workorder_ids = set(participation_ids)
        if has_global:
            # Buscar todas as regras globais com criado_em
            global_rules = list(CollaboratorCommissionRule.objects.filter(collaborator=collaborator, apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL, is_active=True))
            for rule in global_rules:
                workorder_ids |= set(
                    WorkOrder.objects.filter(
                        workshop=collaborator.workshop,
                        budget_type="sale",
                        status=WorkOrderStatus.APPROVED,
                        criado_em__gte=rule.criado_em,
                    ).values_list("id", flat=True)
                )

        workorders = list(
            WorkOrder.objects.filter(pk__in=workorder_ids)
            .select_related("workshop", "budget")
            .prefetch_related("payments", "collaborators")
            .order_by("id")
        )
        existing_payroll_lookup = {
            (p.reference_year, p.reference_month): p
            for p in collaborator.payrolls.all()
        } if hasattr(collaborator, "payrolls") else {}

        synced_entries: list[CollaboratorCommissionEntry] = []
        protected_ids: set[int] = set()
        for wo in workorders:
            if not _workorder_can_generate_commission(wo):
                continue
            # Resolve reference por WO
            commission_reference = _resolve_commission_reference_date(wo)
            effective_reference = _resolve_payroll_reference_date_from_lookup(
                collaborator=collaborator,
                reference_date=commission_reference,
                lock_reference=lock_reference,
                existing_payroll_lookup=existing_payroll_lookup,
            )
            if effective_reference.year != resolved.year or effective_reference.month != resolved.month:
                continue
            protected_ids.add(wo.pk)
            # Delegar ao gerador por WO (que já é idempotente)
            entries = self.generate_commissions_for_workorder(workorder=wo, reference_date=commission_reference)
            # Filtrar apenas deste colaborador
            synced_entries.extend([e for e in entries if e.collaborator_id == collaborator.pk])

        # Limpeza de stale FORECAST fora das protected
        stale = CollaboratorCommissionEntry.objects.filter(
            collaborator=collaborator, reference_year=resolved.year, reference_month=resolved.month, status=CollaboratorCommissionEntry.Status.FORECAST
        )
        if protected_ids:
            stale = stale.exclude(workorder_id__in=protected_ids)
        stale.delete()
        return synced_entries

    def _upsert_entry(
        self,
        *,
        collaborator: WorkshopCollaborator,
        workorder: WorkOrder,
        workshop,
        origin: str,
        rule: CollaboratorCommissionRule | None,
        base_amount: Money,
        pool_amount: Money,
        distribution_pct: Decimal,
        commission_amount: Money,
        reference: date,
        is_fixed: bool,
    ) -> CollaboratorCommissionEntry | None:
        # Determinar percentage salvo: para fixed é 0, para pct é rule.percentage
        if is_fixed:
            stored_pct = Decimal("0")
        elif rule is not None:
            stored_pct = Decimal(str(rule.percentage or 0))
        else:
            stored_pct = Decimal("0")

        # Busca entry existente (lock)
        entry_qs = CollaboratorCommissionEntry.objects.select_for_update().filter(
            collaborator=collaborator, workorder=workorder, commission_origin=origin
        )
        existing = entry_qs.first()
        if existing is None:
            entry = CollaboratorCommissionEntry.objects.create(
                workshop=workshop,
                collaborator=collaborator,
                workorder=workorder,
                origin=CollaboratorCommissionEntry.Origin.WORKORDER,
                commission_origin=origin,
                commission_rule=rule,
                is_fixed_amount=is_fixed,
                reference_year=reference.year,
                reference_month=reference.month,
                percentage=stored_pct,
                base_amount=base_amount,
                pool_amount=pool_amount,
                distribution_percentage=distribution_pct,
                commission_amount=commission_amount,
                status=CollaboratorCommissionEntry.Status.FORECAST,
            )
            return entry

        # PAID é imutável em valores
        if existing.status == CollaboratorCommissionEntry.Status.PAID:
            update_fields: list[str] = []
            if existing.workshop_id != workshop.pk:
                existing.workshop = workshop
                update_fields.append("workshop")
            if existing.reference_year != reference.year:
                existing.reference_year = reference.year
                update_fields.append("reference_year")
            if existing.reference_month != reference.month:
                existing.reference_month = reference.month
                update_fields.append("reference_month")
            if existing.percentage != stored_pct:
                existing.percentage = stored_pct
                update_fields.append("percentage")
            if update_fields:
                existing.save(update_fields=update_fields)
            return existing

        # FORECAST: atualizar tudo
        existing.workshop = workshop
        existing.reference_year = reference.year
        existing.reference_month = reference.month
        existing.percentage = stored_pct
        existing.base_amount = base_amount
        existing.pool_amount = pool_amount
        existing.distribution_percentage = distribution_pct
        existing.commission_amount = commission_amount
        existing.commission_rule = rule
        existing.is_fixed_amount = is_fixed
        existing.status = CollaboratorCommissionEntry.Status.FORECAST
        existing.paid_at = None
        existing.save(
            update_fields=[
                "workshop",
                "reference_year",
                "reference_month",
                "percentage",
                "base_amount",
                "pool_amount",
                "distribution_percentage",
                "commission_amount",
                "commission_rule",
                "is_fixed_amount",
                "status",
                "paid_at",
            ]
        )
        return existing
