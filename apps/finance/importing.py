from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q
from django.utils import timezone
from djmoney.money import Money

from apps.core.infrastructure.importing.base import BaseRowImportAdapter
from apps.core.infrastructure.importing.schema import FieldType, ImportEntitySchema, ImportField, ImportRowError
from apps.finance.models import FinancialGroup, PaymentMethod
from apps.finance.models.financial_movement import FinancialMovement
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


def _resolve_payment_method(workshop: Workshop, name: str) -> PaymentMethod:
    method = PaymentMethod.objects.filter(workshop=workshop, description__iexact=name.strip()).first()
    if method is None:
        raise ImportRowError(f"Forma de pagamento não encontrada: '{name}'.")
    return method


def _resolve_budget_plan(workshop: Workshop, name: str) -> FinancialGroup:
    plan = FinancialGroup.objects.filter(workshop=workshop).filter(Q(name__iexact=name.strip()) | Q(code__iexact=name.strip())).first()
    if plan is None:
        raise ImportRowError(f"Plano orçamentário não encontrado: '{name}'.")
    return plan


def _resolve_supplier(workshop: Workshop, name: str) -> Supplier | None:
    if not name.strip():
        return None
    supplier = Supplier.objects.filter(workshop=workshop, name__iexact=name.strip()).first()
    if supplier is None:
        raise ImportRowError(f"Fornecedor não encontrado: '{name}'.")
    return supplier


class PayableImportAdapter(BaseRowImportAdapter):
    entity_key = "payables"
    label = "Contas a pagar"
    permission_app_label = "finance"
    permission_model = "financialmovement"
    permission_codename = "add_financialmovement"

    def get_schema(self, workshop: Workshop, *, options: dict[str, Any] | None = None) -> ImportEntitySchema:
        return ImportEntitySchema(
            entity_key=self.entity_key,
            label=self.label,
            description="Cria lançamentos de contas a pagar (DEBIT).",
            fields=(
                ImportField("description", "Descrição", required=True, field_type=FieldType.TEXT),
                ImportField("gross_amount", "Valor bruto", required=True, field_type=FieldType.MONEY, help_text="Se vazio ou inválido, usa R$ 0,00"),
                ImportField("due_date", "Data de vencimento", required=True, field_type=FieldType.DATE),
                ImportField("payment_method", "Forma de pagamento", required=True, help_text="Descrição já cadastrada"),
                ImportField("budget_plan", "Plano orçamentário", required=True, help_text="Nome ou código já cadastrado"),
                ImportField("entry_date", "Data de lançamento", field_type=FieldType.DATE),
                ImportField("supplier", "Fornecedor", help_text="Razão social já cadastrada"),
                ImportField("nf_number", "Número da NF"),
                ImportField("is_paid", "Pago", field_type=FieldType.BOOLEAN),
                ImportField("financial_observation", "Observação", field_type=FieldType.TEXT),
            ),
        )

    def create_row(
        self,
        workshop: Workshop,
        mapped: dict[str, Any],
        *,
        user: AbstractBaseUser | None = None,
        options: dict[str, Any] | None = None,
    ) -> int | None:
        description = str(mapped.get("description") or "").strip()
        if not description:
            raise ImportRowError("Descrição é obrigatória.")

        gross = mapped.get("gross_amount")
        gross_decimal = Decimal(str(gross)) if gross is not None else Decimal("0.00")
        due_date = mapped.get("due_date")
        if due_date is None:
            raise ImportRowError("Data de vencimento é obrigatória.")

        payment_method = _resolve_payment_method(workshop, str(mapped.get("payment_method") or ""))
        budget_plan = _resolve_budget_plan(workshop, str(mapped.get("budget_plan") or ""))
        supplier = _resolve_supplier(workshop, str(mapped.get("supplier") or ""))

        gross_money = Money(gross_decimal, "BRL")
        movement = FinancialMovement(
            workshop=workshop,
            user=user if user is not None and getattr(user, "is_authenticated", False) else None,
            direction=FinancialMovement.MovementDirection.DEBIT,
            movement_kind=FinancialMovement.MovementKind.DEFAULT,
            current_step=4,
            description=description,
            gross_amount=gross_money,
            amount=gross_money,
            due_date=due_date,
            entry_date=mapped.get("entry_date") or timezone.localdate(),
            payment_method=payment_method,
            budget_plan=budget_plan,
            supplier=supplier,
            nf_number=str(mapped.get("nf_number") or "") or None,
            is_paid=bool(mapped["is_paid"]) if mapped.get("is_paid") is not None else False,
            financial_observation=str(mapped.get("financial_observation") or "") or None,
            discount_mode=FinancialMovement.DiscountMode.NONE,
        )
        movement.save()
        return int(movement.pk)


def register_payable_import_adapter() -> None:
    from apps.core.infrastructure.importing.registry import register_adapter

    register_adapter(PayableImportAdapter())
