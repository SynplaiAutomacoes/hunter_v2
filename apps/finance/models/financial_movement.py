from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from django.db import models

from apps.core.infrastructure.models import TimeStampedModel
from djmoney.models.fields import MoneyField

from django.conf import settings
from django.utils import timezone
from djmoney.money import Money

from apps.finance.models import PaymentMethod, FinancialGroup
from apps.finance.models.bank_account import BankAccount


def _format_money_for_report(value: Any) -> str:
    from decimal import Decimal

    amount: Decimal
    if hasattr(value, "amount"):
        amount = value.amount
    else:
        amount = Decimal(str(value or 0))
    amount = amount.quantize(Decimal("0.01"))
    integer_part, decimal_part = f"{amount:.2f}".split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", ".")
    return f"R$ {grouped_integer},{decimal_part}"


class FinancialMovement(TimeStampedModel):
    class MovementDirection(models.TextChoices):
        CREDIT = "CREDIT", "Contas a receber (receita)"
        DEBIT = "DEBIT", "Contas a pagar (despesa)"

    class MovementKind(models.TextChoices):
        DEFAULT = "DEFAULT", "Padrão"
        WORKORDER_PARENT = "WORKORDER_PARENT", "OS Pai"
        WORKORDER_CARD_FEE = "WORKORDER_CARD_FEE", "Taxa da Maquininha"
        GROUP_PARENT = "GROUP_PARENT", "Agrupamento"

    class PayrollComponent(models.TextChoices):
        SALARY = "SALARY", "Salário"
        BENEFIT = "BENEFIT", "Benefícios"
        TRANSPORT = "TRANSPORT", "Vale Transporte"
        COMMISSION = "COMMISSION", "Comissão"

    class DiscountMode(models.TextChoices):
        NONE = "NONE", "Sem desconto"
        AMOUNT = "AMOUNT", "Desconto em reais (R$)"
        PERCENTAGE = "PERCENTAGE", "Desconto em percentual (%)"

    workshop = models.ForeignKey(to="workshops.Workshop", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    current_step = models.PositiveSmallIntegerField(default=1)
    movement_kind = models.CharField(max_length=50, choices=MovementKind.choices, default=MovementKind.DEFAULT)
    workorder = models.ForeignKey("workorder.WorkOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="financial_movements")
    workorder_payment = models.ForeignKey("workorder.WorkOrderPaymentMethod", on_delete=models.CASCADE, null=True, blank=True, related_name="financial_movements")
    reversal_of = models.OneToOneField("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reversal_entry")
    movement_group = models.ForeignKey("finance.MovementGroup", on_delete=models.CASCADE, null=True, blank=True, related_name="financial_movements")
    payroll = models.ForeignKey("collaborators.CollaboratorPayroll", on_delete=models.CASCADE, null=True, blank=True, related_name="financial_movements")
    payroll_component = models.CharField(max_length=32, choices=PayrollComponent.choices, null=True, blank=True)
    payroll_benefit = models.ForeignKey(
        "collaborators.CollaboratorBenefit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_financial_movements",
        verbose_name="Benefício da folha",
    )

    # Origem
    source = models.ForeignKey(to="sources.Source", verbose_name="Origem", null=True, blank=True, on_delete=models.PROTECT)
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", verbose_name="Colaborador", on_delete=models.SET_NULL, related_name="financial_movements", null=True, blank=True)
    supplier = models.ForeignKey("suppliers.Supplier", verbose_name="Fornecedor", on_delete=models.SET_NULL, null=True, blank=True, related_name="financial_movements")

    # Itens
    description = models.TextField(verbose_name="Descrição dos Itens", blank=True, null=True)
    items_observation = models.TextField(verbose_name="Observações dos Itens", blank=True, null=True)

    # Financeiro
    direction = models.CharField(max_length=50, verbose_name="Tipo", choices=MovementDirection.choices, blank=True, null=True)
    payment_method = models.ForeignKey(PaymentMethod, verbose_name="Forma de Pagamento", on_delete=models.PROTECT, blank=True, null=True)
    nf_number = models.CharField(max_length=50, verbose_name="Número da NF", blank=True, null=True)
    entry_date = models.DateField(verbose_name="Data de Lançamento", default=timezone.localdate)
    gross_amount = MoneyField(verbose_name="Valor Bruto", max_digits=14, decimal_places=2, null=True, blank=True)
    discount_mode = models.CharField(verbose_name="Tipo de Desconto", max_length=12, choices=DiscountMode.choices, default=DiscountMode.NONE)
    discount_value = MoneyField(verbose_name="Desconto (R$)", max_digits=14, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(verbose_name="Desconto (%)", max_digits=7, decimal_places=4, default=Decimal("0.00"))
    amount = MoneyField(verbose_name="Valor", max_digits=14, decimal_places=2, default=0, null=True)
    due_date = models.DateField(verbose_name="Data de Vencimento", blank=True, null=True)
    is_paid = models.BooleanField(verbose_name="Pago", default=False)
    is_reconciled = models.BooleanField(verbose_name="Conciliado", default=False)
    budget_plan = models.ForeignKey(FinancialGroup, on_delete=models.PROTECT, verbose_name="Plano Orçamentário", blank=True, null=True)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, verbose_name="Conta Bancária", blank=True, null=True)
    attachment = models.FileField(upload_to="financial/attachments/", null=True, blank=True, verbose_name="Anexo")
    financial_observation = models.TextField(verbose_name="Observação Financeira", blank=True, null=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["payroll", "payroll_component", "budget_plan"],
                condition=models.Q(payroll__isnull=False, payroll_component__isnull=False, payroll_benefit__isnull=True),
                name="unique_payroll_component_movement",
            ),
            models.UniqueConstraint(
                fields=["payroll", "payroll_benefit"],
                condition=models.Q(payroll__isnull=False, payroll_component="BENEFIT", payroll_benefit__isnull=False),
                name="unique_payroll_benefit_movement",
            ),
        ]
        indexes = [
            models.Index(fields=["workshop", "payroll"]),
            models.Index(fields=["workshop", "payroll_component"]),
            models.Index(fields=["workshop", "due_date"], name="fin_mov_ws_due_idx"),
            models.Index(fields=["workshop", "direction", "movement_kind"], name="fin_mov_ws_dir_kind_idx"),
            models.Index(fields=["workshop", "is_paid", "due_date"], name="fin_mov_ws_paid_due_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.gross_amount is None:
            self.gross_amount = self.amount or Money(Decimal("0.00"), "BRL")
        self._sync_net_amount_from_discount()
        if not self.budget_plan:
            self._auto_assign_budget_plan()

        super().save(*args, **kwargs)

    def _sync_net_amount_from_discount(self) -> None:
        gross_amount = self.gross_amount or Money(Decimal("0.00"), "BRL")
        gross_value = Decimal(str(gross_amount.amount or 0))
        discount = Decimal("0.00")

        if self.discount_mode == self.DiscountMode.AMOUNT:
            discount = Decimal(str((self.discount_value or Money(0, gross_amount.currency)).amount or 0))
        elif self.discount_mode == self.DiscountMode.PERCENTAGE:
            discount = gross_value * Decimal(str(self.discount_percentage or 0)) / Decimal("100")

        discount = min(max(discount, Decimal("0.00")), gross_value)
        self.amount = Money(
            (gross_value - discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            gross_amount.currency,
        )

    def _auto_assign_budget_plan(self) -> None:
        """
        Lógica interna para atribuir automaticamente o Plano Orçamentário (FinancialGroup)
        baseado na descrição ou na presença de uma Ordem de Serviço.
        """
        # Regra 1: Taxa da Maquininha
        if self.description == "Pagamento da taxa da maquininha":
            target_group = FinancialGroup.objects.filter(workshop=self.workshop, name__iexact="Taxa de Maquininhas").first()
            if target_group:
                self.budget_plan = target_group
                return

        # Regra 2: Movimentação vinculada a uma Ordem de Serviço
        if self.workorder:
            target_group = FinancialGroup.objects.filter(workshop=self.workshop, name__iexact="Vendas").first()
            if target_group is None:
                target_group = FinancialGroup.objects.filter(workshop=self.workshop, name__iexact="Receitas").first()
            if target_group:
                self.budget_plan = target_group
                return
        return

    @staticmethod
    def _format_report_money(value: object) -> str:
        return _format_money_for_report(value)

    @property
    def report_paid_indicator(self) -> str | dict[str, str]:
        return {
            "icon": "check_circle" if self.is_paid else "cancel",
            "class": "text-success" if self.is_paid else "text-error",
            "label": "Pago" if self.is_paid else "Não pago",
        }

    @property
    def report_reconciliation_indicator(self) -> dict[str, str]:
        return {
            "icon": "check_circle" if self.is_reconciled else "schedule",
            "class": "text-success" if self.is_reconciled else "text-warning",
            "label": "Conciliado" if self.is_reconciled else "Aguardando conciliação",
        }

    @property
    def report_direction_badge(self) -> dict[str, str]:
        badge_class = "badge-success"
        if self.direction == self.MovementDirection.DEBIT:
            badge_class = "badge-error"

        direction_text = {
            self.MovementDirection.CREDIT: "Contas a receber",
            self.MovementDirection.DEBIT: "Contas a pagar",
        }.get(self.direction, "-")

        return {
            "text": direction_text,
            "class": badge_class,
        }

    @property
    def report_total_display(self) -> dict[str, str]:
        sign = "+"
        text_class = "text-success"
        if self.direction == self.MovementDirection.DEBIT:
            sign = "-"
            text_class = "text-error"

        return {
            "text": f"{sign} {self._format_report_money(self.amount)}",
            "class": f"{text_class} font-semibold whitespace-nowrap",
        }

    @property
    def report_agent_display(self) -> str:
        if self.workorder_id:
            customer = getattr(getattr(self.workorder, "budget", None), "customer", None)
            return f"O.S #{str(self.workorder.budget.number)} - {getattr(customer, 'name', '-') or '-'}"

        if self.collaborator_id:
            return str(self.collaborator.name)

        if self.supplier_id:
            return str(self.supplier.name)

        if self.source_id:
            return str(self.source.name)

        return "-"

    @property
    def report_origin_display(self) -> str:
        return str(self.nf_number or "-")

    @property
    def report_description_display(self) -> str:
        return str(self.description or "-")

    @property
    def report_budget_plan_display(self) -> str:
        budget_plan = getattr(self, "budget_plan", None)
        if budget_plan is not None:
            return str(budget_plan)
        return "-"

    @property
    def report_bank_account_display(self) -> str:
        bank_account = getattr(self, "bank_account", None)
        if bank_account is not None:
            return str(bank_account)
        return "-"

    @property
    def report_payment_method_display(self) -> str:
        payment_method = getattr(self, "payment_method", None)
        if payment_method is not None:
            return str(payment_method)
        return "-"
