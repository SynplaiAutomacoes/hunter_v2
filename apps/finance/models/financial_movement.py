from tokenize import blank_re

from django.db import models

from apps.core.models import TimeStampedModel
from djmoney.models.fields import MoneyField

from django.conf import settings

from apps.finance.forms.emission_ui import format_money
from apps.finance.models import PaymentMethod, FinancialGroup
from apps.finance.models.bank_account import BankAccount


class FinancialMovement(TimeStampedModel):
    class MovementDirection(models.TextChoices):
        CREDIT = "CREDIT", "Contas a receber (receita)"
        DEBIT = "DEBIT", "Contas a pagar (despesa)"

    class MovementKind(models.TextChoices):
        DEFAULT = "DEFAULT", "Padrão"
        WORKORDER_PARENT = "WORKORDER_PARENT", "OS Pai"
        WORKORDER_CARD_FEE = "WORKORDER_CARD_FEE", "Taxa da Maquininha"

    class DreTopic(models.TextChoices):
        RECEITA_BRUTA_VENDAS_E_SERVICOS = "receita_bruta_vendas_e_servicos", "Receita Bruta de Vendas e Serviços"
        CUSTOS_MERCADORIAS_VENDIDAS = "custos_mercadorias_vendidas", "Custos Mercadorias Vendidas"
        RECEITAS_FINANCEIRAS = "receitas_financeiras", "Receitas Financeiras"
        DESPESAS_FINANCEIRAS = "despesas_financeiras", "Despesas Financeiras"

    workshop = models.ForeignKey(to="workshops.Workshop", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    current_step = models.PositiveSmallIntegerField(default=1)
    movement_kind = models.CharField(max_length=30, choices=MovementKind.choices, default=MovementKind.DEFAULT)
    workorder = models.ForeignKey("workorder.WorkOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="financial_movements")
    workorder_payment = models.ForeignKey("workorder.WorkOrderPaymentMethod", on_delete=models.CASCADE, null=True, blank=True, related_name="financial_movements")

    # Origem
    source = models.ForeignKey(to="sources.Source", verbose_name="Origem", null=True, blank=True, on_delete=models.PROTECT)
    collaborator = models.ForeignKey("collaborators.WorkshopCollaborator", verbose_name="Colaborador", on_delete=models.SET_NULL, related_name="financial_movements", null=True, blank=True)
    supplier = models.ForeignKey("suppliers.Supplier",  verbose_name="Fornecedor", on_delete=models.SET_NULL, null=True, blank=True, related_name="financial_movements")

    # Itens
    description = models.CharField(verbose_name="Descrição dos Itens", max_length=255, blank=True, null=True)
    items_observation = models.TextField(verbose_name="Observações dos Itens", blank=True, null=True)

    # Financeiro
    direction = models.CharField(max_length=15, verbose_name="Tipo", choices=MovementDirection.choices, default=MovementDirection.DEBIT, blank=True, null=True)
    payment_method = models.ForeignKey(PaymentMethod, verbose_name="Forma de Pagamento", on_delete=models.PROTECT, blank=True, null=True)
    nf_number = models.CharField(max_length=50, verbose_name="Número da NF", blank=True, null=True)
    amount = MoneyField(verbose_name="Valor", max_digits=14, decimal_places=2, default=0, null=True)
    due_date = models.DateField(verbose_name="Data de Vencimento", blank=True, null=True)
    is_paid = models.BooleanField(verbose_name="Pago", default=False)
    budget_plan = models.ForeignKey(FinancialGroup, on_delete=models.PROTECT, verbose_name="Plano Orçamentário", blank=True, null=True)
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, verbose_name="Conta Bancária", blank=True, null=True)
    attachment = models.FileField(upload_to="financial/attachments/", null=True, blank=True, verbose_name="Anexo")
    financial_observation = models.TextField(verbose_name="Observação Financeira", blank=True, null=True)

    @staticmethod
    def _format_report_money(value: object) -> str:
        return format_money(value)

    @property
    def report_paid_indicator(self) -> str | dict[str, str]:
        return {
            "icon": "check_circle" if self.is_paid else "cancel",
            "class": "text-success" if self.is_paid else "text-error",
            "label": "Sim" if self.is_paid else "Não",
        }

    @property
    def report_direction_badge(self) -> dict[str, str]:
        badge_class = "badge-success"
        if self.direction == self.MovementDirection.DEBIT:
            badge_class = "badge-error"

        direction_text = {
            self.MovementDirection.CREDIT: "Crédito",
            self.MovementDirection.DEBIT: "Débito",
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
            return f"O.S #{str(self.workorder.budget.pk)} - {getattr(customer, 'name', '-') or '-'}"

        if self.collaborator_id:
            return str(self.collaborator.name)

        if self.supplier_id:
            return str(self.supplier.name)

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
