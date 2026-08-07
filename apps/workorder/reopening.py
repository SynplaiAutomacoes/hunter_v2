from __future__ import annotations

from django.db import transaction

from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WORKORDER_REOPENABLE_STATUSES, WorkOrder, WorkOrderHistory


class WorkOrderReopenError(Exception):
    pass


def reopen_workorder(*, workorder: WorkOrder, user, reason: str) -> None:
    """Reabre uma O.S. sem estornar o estoque já consumido.

    As peças consumidas (movimentações ``EXIT`` aprovadas) permanecem consumidas,
    pois já foram fisicamente utilizadas. O estoque só será reconciliado por delta
    na finalização (``approve_workorder_with_stock``): consome apenas acréscimos e
    devolve excedentes em caso de redução/remoção de itens.
    """
    if not workorder.can_reopen:
        raise WorkOrderReopenError("Somente ordens de serviço entregues, canceladas ou rejeitadas podem ser reabertas.")

    reason = str(reason or "").strip()
    if not reason:
        raise WorkOrderReopenError("Informe a justificativa para reabrir a O.S.")

    with transaction.atomic():
        locked_workorder = WorkOrder.objects.select_for_update().select_related("budget", "workshop").get(pk=workorder.pk)
        if locked_workorder.status not in WORKORDER_REOPENABLE_STATUSES:
            raise WorkOrderReopenError("Somente ordens de serviço entregues, canceladas ou rejeitadas podem ser reabertas.")

        FinancialMovement.objects.select_for_update().filter(
            workorder=locked_workorder,
            movement_kind__in=[
                FinancialMovement.MovementKind.WORKORDER_PARENT,
                FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            ],
        ).delete()

        WorkOrderHistory.objects.create(
            workorder=locked_workorder,
            user=user,
            action=WorkOrderHistory.Action.REOPENED,
            reason=reason,
        )

        locked_workorder.reopen(reason=reason)

        sync_workorder_collaborator_payrolls(workorder=locked_workorder)
