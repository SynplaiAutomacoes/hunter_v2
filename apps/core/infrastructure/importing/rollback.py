from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.db.models import Model, ProtectedError, RestrictedError
from django.utils import timezone

from apps.core.infrastructure.models.data_import import DataImportBatch, DataImportBatchItem


@dataclass(slots=True)
class RollbackItemOutcome:
    item_id: int
    object_id: int | None
    status: str
    detail: str = ""


@dataclass(slots=True)
class RollbackPlan:
    deletable: list[DataImportBatchItem] = field(default_factory=list)
    blocked: list[tuple[DataImportBatchItem, str]] = field(default_factory=list)
    missing: list[DataImportBatchItem] = field(default_factory=list)

    @property
    def deletable_count(self) -> int:
        return len(self.deletable)

    @property
    def blocked_count(self) -> int:
        return len(self.blocked)

    @property
    def missing_count(self) -> int:
        return len(self.missing)


@dataclass(slots=True)
class RollbackResult:
    deleted_count: int = 0
    blocked_count: int = 0
    missing_count: int = 0
    outcomes: list[RollbackItemOutcome] = field(default_factory=list)
    batch_status: str = ""


ENTITY_LABELS: dict[str, str] = {
    "customers": "Clientes",
    "suppliers": "Fornecedores",
    "products": "Produtos",
    "services": "Serviços",
    "kits": "Kits",
    "payables": "Contas a pagar",
}


def get_entity_label(entity_key: str) -> str:
    return ENTITY_LABELS.get(entity_key, entity_key)


def _get_model_for_entity(entity_key: str) -> type[Model]:
    if entity_key == "customers":
        from apps.customer.models import Customer

        return Customer
    if entity_key == "suppliers":
        from apps.suppliers.models import Supplier

        return Supplier
    if entity_key == "products":
        from apps.catalog.models.products import Product

        return Product
    if entity_key == "services":
        from apps.catalog.models.services import Service

        return Service
    if entity_key == "kits":
        from apps.catalog.models.kits import Kit

        return Kit
    if entity_key == "payables":
        from apps.finance.models.financial_movement import FinancialMovement

        return FinancialMovement
    raise ValueError(f"Entidade de importação desconhecida: {entity_key}")


def _can_delete_customer(obj: Any) -> tuple[bool, str]:
    if obj.vehicles.exists():
        return False, "Cliente possui veículos vinculados."
    if hasattr(obj, "budgets") and obj.budgets.exists():
        return False, "Cliente possui orçamentos vinculados."
    if hasattr(obj, "workorders") and obj.workorders.exists():
        return False, "Cliente possui ordens de serviço vinculadas."
    return True, ""


def _can_delete_supplier(obj: Any) -> tuple[bool, str]:
    if hasattr(obj, "financial_movements") and obj.financial_movements.exists():
        return False, "Fornecedor possui movimentações financeiras."
    if hasattr(obj, "stock_products") and obj.stock_products.exists():
        return False, "Fornecedor vinculado a estoque."
    if hasattr(obj, "movements") and obj.movements.exists():
        return False, "Fornecedor vinculado a movimentações de estoque."
    return True, ""


def _stock_has_non_import_movements(obj: Any) -> bool:
    stock = getattr(obj, "stock_products", None)
    if stock is None:
        return False
    # Ajustes de estoque da importação (is_stock_adjustment) não bloqueiam o rollback.
    return stock.movements.filter(is_stock_adjustment=False).exists()


def _can_delete_product(obj: Any) -> tuple[bool, str]:
    if obj.budgetitem_set.exists():
        return False, "Produto já utilizado em orçamento."
    if obj.workorderitem_set.exists():
        return False, "Produto já utilizado em ordem de serviço."
    if obj.product_kits.exists():
        return False, "Produto faz parte de um kit."
    if obj.budgetkititemoverride_set.exists() or obj.workorderkititemoverride_set.exists():
        return False, "Produto utilizado em override de kit."
    if _stock_has_non_import_movements(obj):
        return False, "Produto possui movimentações de estoque além da importação."
    return True, ""


def _can_delete_service(obj: Any) -> tuple[bool, str]:
    if obj.budgetitem_set.exists() or obj.workorderitem_set.exists():
        return False, "Serviço já utilizado em orçamento ou OS."
    if obj.service_kits.exists():
        return False, "Serviço faz parte de um kit."
    if obj.budgetkititemoverride_set.exists() or obj.workorderkititemoverride_set.exists():
        return False, "Serviço utilizado em override de kit."
    return True, ""


def _can_delete_kit(obj: Any) -> tuple[bool, str]:
    if obj.budgetitem_set.exists() or obj.workorderitem_set.exists():
        return False, "Kit já utilizado em orçamento ou OS."
    return True, ""


def _can_delete_payable(obj: Any) -> tuple[bool, str]:
    if getattr(obj, "is_paid", False):
        return False, "Lançamento já está pago."
    if getattr(obj, "is_reconciled", False):
        return False, "Lançamento já está conciliado."
    if getattr(obj, "movement_group_id", None):
        return False, "Lançamento faz parte de um agrupamento."
    if getattr(obj, "payroll_id", None):
        return False, "Lançamento vinculado à folha de pagamento."
    if getattr(obj, "workorder_id", None):
        return False, "Lançamento vinculado a ordem de serviço."
    return True, ""


def can_delete_imported_object(entity_key: str, obj: Model) -> tuple[bool, str]:
    checkers = {
        "customers": _can_delete_customer,
        "suppliers": _can_delete_supplier,
        "products": _can_delete_product,
        "services": _can_delete_service,
        "kits": _can_delete_kit,
        "payables": _can_delete_payable,
    }
    checker = checkers.get(entity_key)
    if checker is None:
        return False, "Esta importação não pode ser desfeita."
    return checker(obj)


def build_rollback_plan(batch: DataImportBatch) -> RollbackPlan:
    plan = RollbackPlan()
    if not batch.can_rollback and batch.status == DataImportBatch.Status.ROLLED_BACK:
        return plan

    model = _get_model_for_entity(batch.entity_key)
    # ACTIVE e BLOCKED: permite nova tentativa após corrigir regras (ex.: estoque da importação).
    active_items = list(
        batch.items.filter(
            success=True,
            object_id__isnull=False,
            rollback_status__in=[
                DataImportBatchItem.RollbackStatus.ACTIVE,
                DataImportBatchItem.RollbackStatus.BLOCKED,
            ],
        ).order_by("row_number", "id")
    )
    if not active_items:
        return plan

    object_ids = [int(item.object_id) for item in active_items if item.object_id is not None]
    objects_by_id = model.objects.in_bulk(object_ids)

    for item in active_items:
        object_id = int(item.object_id) if item.object_id is not None else None
        if object_id is None:
            plan.missing.append(item)
            continue
        obj = objects_by_id.get(object_id)
        if obj is None:
            plan.missing.append(item)
            continue
        if getattr(obj, "workshop_id", None) not in (None, batch.workshop_id):
            plan.blocked.append((item, "Registro não pertence à oficina do lote."))
            continue
        ok, reason = can_delete_imported_object(batch.entity_key, obj)
        if ok:
            plan.deletable.append(item)
        else:
            plan.blocked.append((item, reason or "Registro em uso."))
    return plan


def execute_rollback(batch: DataImportBatch, *, force_partial: bool = False) -> RollbackResult:
    """Delete imported objects that are still safe to remove.

    If there are blocked items and ``force_partial`` is False, raises ValueError
    so the UI can show the warning first.
    """
    if batch.status == DataImportBatch.Status.ROLLED_BACK:
        raise ValueError("Esta importação já foi totalmente desfeita.")

    plan = build_rollback_plan(batch)
    if plan.blocked and not force_partial:
        raise ValueError("Há registros em uso. Confirme para remover apenas o possível.")

    model = _get_model_for_entity(batch.entity_key)
    result = RollbackResult()

    with transaction.atomic():
        for item, reason in plan.blocked:
            item.rollback_status = DataImportBatchItem.RollbackStatus.BLOCKED
            item.rollback_detail = reason
            item.save(update_fields=["rollback_status", "rollback_detail", "atualizado_em"])
            result.blocked_count += 1
            result.outcomes.append(
                RollbackItemOutcome(item_id=item.pk, object_id=item.object_id, status="blocked", detail=reason)
            )

        for item in plan.missing:
            item.rollback_status = DataImportBatchItem.RollbackStatus.MISSING
            item.rollback_detail = "Registro já não existe."
            item.save(update_fields=["rollback_status", "rollback_detail", "atualizado_em"])
            result.missing_count += 1
            result.outcomes.append(
                RollbackItemOutcome(item_id=item.pk, object_id=item.object_id, status="missing", detail=item.rollback_detail)
            )

        deletable_ids = [int(item.object_id) for item in plan.deletable if item.object_id is not None]
        objects_by_id = model.objects.in_bulk(deletable_ids)

        for item in plan.deletable:
            object_id = int(item.object_id) if item.object_id is not None else None
            obj = objects_by_id.get(object_id) if object_id is not None else None
            if obj is None:
                item.rollback_status = DataImportBatchItem.RollbackStatus.MISSING
                item.rollback_detail = "Registro já não existe."
                item.save(update_fields=["rollback_status", "rollback_detail", "atualizado_em"])
                result.missing_count += 1
                result.outcomes.append(
                    RollbackItemOutcome(item_id=item.pk, object_id=object_id, status="missing", detail=item.rollback_detail)
                )
                continue
            try:
                obj.delete()
            except (ProtectedError, RestrictedError):
                item.rollback_status = DataImportBatchItem.RollbackStatus.BLOCKED
                item.rollback_detail = "Registro protegido por vínculos no sistema."
                item.save(update_fields=["rollback_status", "rollback_detail", "atualizado_em"])
                result.blocked_count += 1
                result.outcomes.append(
                    RollbackItemOutcome(item_id=item.pk, object_id=object_id, status="blocked", detail=item.rollback_detail)
                )
                continue
            except Exception as exc:  # noqa: BLE001
                item.rollback_status = DataImportBatchItem.RollbackStatus.BLOCKED
                item.rollback_detail = str(exc)[:250] or "Falha ao remover."
                item.save(update_fields=["rollback_status", "rollback_detail", "atualizado_em"])
                result.blocked_count += 1
                result.outcomes.append(
                    RollbackItemOutcome(item_id=item.pk, object_id=object_id, status="blocked", detail=item.rollback_detail)
                )
                continue

            item.rollback_status = DataImportBatchItem.RollbackStatus.DELETED
            item.rollback_detail = "Removido ao desfazer a importação."
            item.save(update_fields=["rollback_status", "rollback_detail", "atualizado_em"])
            result.deleted_count += 1
            result.outcomes.append(
                RollbackItemOutcome(item_id=item.pk, object_id=object_id, status="deleted", detail=item.rollback_detail)
            )

        still_active = batch.items.filter(
            success=True,
            object_id__isnull=False,
            rollback_status=DataImportBatchItem.RollbackStatus.ACTIVE,
        ).exists()
        has_blocked = batch.items.filter(rollback_status=DataImportBatchItem.RollbackStatus.BLOCKED).exists()

        if still_active or has_blocked:
            batch.status = DataImportBatch.Status.PARTIALLY_ROLLED_BACK
        else:
            batch.status = DataImportBatch.Status.ROLLED_BACK
        batch.rolled_back_at = timezone.now()
        batch.save(update_fields=["status", "rolled_back_at", "atualizado_em"])
        result.batch_status = batch.status

    return result
