from __future__ import annotations

from django.db import transaction

from apps.budget.models import Budget, BudgetStatus
from apps.stock.models import StockMovement


class BudgetApprovalError(Exception):
    pass


def approve_budget_with_stock(*, budget: Budget, user=None) -> None:
    local_items = budget.items.filter(is_local=True)
    if local_items.exists():
        raise BudgetApprovalError("Nao e possivel aprovar. Existem itens sem cadastro (locais).")

    with transaction.atomic():
        for item in budget.items.select_related("product"):
            if not item.product_id:
                continue

            stock_product = getattr(item.product, "stock_products", None)
            if stock_product is None:
                raise BudgetApprovalError(f"Produto sem estoque vinculado: {item.product}")

            if stock_product.current_quantity < item.quantity:
                raise BudgetApprovalError(f"Estoque insuficiente para {item.product.referencia}. Disponivel: {stock_product.current_quantity}, Necessario: {item.quantity}")

            stock_product.current_quantity -= item.quantity
            stock_product.save(update_fields=["current_quantity"])

            StockMovement.objects.create(
                workshop=budget.workshop,
                stock_product=stock_product,
                type=StockMovement.MovementType.EXIT,
                quantity=item.quantity,
                status=StockMovement.MovementStatus.APPROVED,
                transcation_by=user,
            )

        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])
