from django.db import models
from django.db.models import PositiveIntegerField
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from apps.core.models import TimeStampedModel


class WorkOrderStatus(models.TextChoices):
    DRAFT = "draft", "Em Aberto"
    APPROVED = "approved", "Aprovado"


class WorkOrder(TimeStampedModel):
    workshop = models.ForeignKey( "workshops.Workshop", on_delete=models.CASCADE, related_name="workorders")
    budget = models.ForeignKey("budget.Budget", on_delete=models.CASCADE, related_name="workorders", help_text="Orçamento Aprovado vinculado à esta O.S.")
    status = models.CharField(verbose_name="Status", max_length=20, choices=WorkOrderStatus.choices, default=WorkOrderStatus.DRAFT)
    
    @property
    def workorder_status_badge(self):
        status_color = {
            WorkOrderStatus.DRAFT: "badge-soft badge-ghost",
            WorkOrderStatus.APPROVED: "badge-success",
        }

        return {"text": WorkOrderStatus(self.status).label, "class": status_color.get(self.status, "badge-ghost")}

    class Meta:
        verbose_name = "Ordem de Serviço"
        verbose_name_plural = "Ordens de Serviço"

    def __str__(self):
        return f"OS #{self.id}"


class WorkOrderPaymentMethod(TimeStampedModel):
    PAYMENT_METHOD_CHOICES = (
        ("CREDITO", "Cartão de Crédito"),
        ("DEBITO", "Cartão de Débito"),
        ("PIX", "Pix"),
        ("DINHEIRO", "Dinheiro"),
        ("BOLETO", "Boleto"),
    )

    workorder = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="payments")
    payment_method = models.CharField(verbose_name="Forma de Pagamento", choices=PAYMENT_METHOD_CHOICES, max_length=20)
    installments_count = PositiveIntegerField(verbose_name="Número de Parcelas", default=1)
    first_installment_amount = MoneyField(verbose_name="Valor da Primeira Parcela", max_digits=14, decimal_places=2, default=0.00)
    remaining_installments_amount = MoneyField(verbose_name="Valor das Parcelas Restantes", max_digits=14, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = "Plano de Pagamento"
        verbose_name_plural = "Planos de Pagamento"

    @property
    def total_paid(self) -> Money:
        return Money(self.first_installment_amount.amount + ((self.installments_count-1) * self.remaining_installments_amount.amount), 'BRL')

    def __str__(self):
        return f"Plano de Pagamento #{self.id} - {self.payment_method}"


class WorkOrderAttachment(TimeStampedModel):
    workorder = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="attachments")
    content = models.BinaryField(null=True, blank=True)
    content_name = models.CharField(max_length=100, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = "Imagem da OS"
        verbose_name_plural = "Imagens da OS"

    def __str__(self):
        return f"Image #{self.id} from Work Order : {self.workorder}"