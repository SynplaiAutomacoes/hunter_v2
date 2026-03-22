from django.db import models
from django.conf import settings
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.finance.models.payment_method import PaymentMethod
from apps.suppliers.models import Supplier
from djmoney.models.fields import MoneyField


class StockProduct(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="stock_products")
    product = models.OneToOneField("catalog.Product", on_delete=models.CASCADE, related_name="stock_products")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_products")
    current_quantity = models.IntegerField(default=0, verbose_name="Estoque Atual")
    minimum_quantity = models.IntegerField(default=0, verbose_name="Estoque Mínimo")
    restock_quantity = models.IntegerField(default=0, verbose_name="Estoque Reposição")
    last_nf = models.CharField(max_length=50, blank=True, null=True, verbose_name="Última NF")

    class Meta:
        verbose_name = "Produto do Estoque"
        verbose_name_plural = "Produtos do Estoque"

    def __str__(self):
        return f"{self.product.name} - {self.current_quantity} unidades"


class StockMovement(TimeStampedModel):
    class MovementType(models.TextChoices):
        ENTRY = "ENTRADA", "Entrada"
        EXIT = "SAIDA", "Saída"

    class MovementStatus(models.TextChoices):
        WAITING = "AGUARDANDO", "Aguardando Aprovação"
        APPROVED = "APROVADO", "Aprovado"
        REJECTED = "REJEITADO", "Rejeitado"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="movements")
    stock_product = models.ForeignKey(StockProduct, on_delete=models.CASCADE, verbose_name="Peça", related_name="movements")
    type = models.CharField(max_length=10, choices=MovementType.choices, verbose_name="Tipo")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, verbose_name="Fornecedor", null=True, blank=True, related_name="movements")
    transcation_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="movements", null=True)
    quantity = models.IntegerField(default=1, verbose_name="Quantidade")
    status = models.CharField(max_length=10, choices=MovementStatus.choices, verbose_name="Status", default=MovementStatus.WAITING)

    class Meta:
        verbose_name = "Movimentação de Estoque"
        verbose_name_plural = "Movimentações de Estoque"

    @property
    def stockmovement_status_badge(self):
        status_color = {
            StockMovement.MovementStatus.WAITING: "badge-soft badge-ghost",
            StockMovement.MovementStatus.APPROVED: "badge-success",
            StockMovement.MovementStatus.REJECTED: "badge-error",
        }

        return {"text": self.get_status_display(), "class": status_color.get(self.status, "badge-ghost")}

    @property
    def stockmovement_type_badge(self):
        status_color = {
            StockMovement.MovementType.EXIT: "badge-error",
            StockMovement.MovementType.ENTRY: "badge-success",
        }

        return {"text": self.get_type_display(), "class": status_color.get(self.type, "badge-ghost")}

    @property
    def get_product_reference(self):
        return self.stock_product.product

    @property
    def location(self):
        return self.stock_product.product.location


class StockPaymentMethod(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="stockpayments")
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, verbose_name="Forma de Pagamento", null=True, blank=True)
    installments_count = models.PositiveIntegerField(verbose_name="Número de Parcelas", default=1)
    first_installment_amount = MoneyField(verbose_name="Valor da primeira parcela", max_digits=14, decimal_places=2, default=0.00)
    remaining_installments_amount = MoneyField(verbose_name="Valor das parcelas restantes", max_digits=14, decimal_places=2, default=0.00)
    due_date = models.DateTimeField(default=timezone.now)
    nf_number = models.CharField(max_length=60, verbose_name="Número da NF", null=False, blank=False)

    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"

    @property
    def total_paid(self):
        return self.first_installment_amount.amount + ((self.installments_count - 1) * self.remaining_installments_amount.amount)


class SefazZipCache(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="sefaz_caches")
    key = models.CharField(max_length=44, verbose_name="Chave de Acesso")
    nf_number = models.CharField(max_length=20, null=True, blank=True)
    issue_date = models.DateTimeField(null=True, blank=True)
    issuer_name = models.CharField(max_length=255, null=True, blank=True)
    issuer_cnpj = models.CharField(max_length=20, null=True, blank=True)
    total_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    is_imported = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Cache do Sefaz (zip)"
        verbose_name_plural = "Cache do Sefaz (zip)"
        unique_together = ("workshop", "key")

    @property
    def nf_number_display(self) -> str:
        from apps.stock.utils import extract_nf_number_from_access_key

        return str(self.nf_number or extract_nf_number_from_access_key(self.key) or "---")


class StockImport(TimeStampedModel):
    class ImportStatus(models.TextChoices):
        DRAFT = "RASCUNHO", "Rascunho"
        COMPLETED = "CONCLUIDO", "Concluído"

    class ImportMethods(models.TextChoices):
        SEFAZ = "SEFAZ", "SEFAZ"
        XML = "XML", "Arquivo XML"
        KEY = "KEY", "Chave de Acesso"
        MANUAL = "MANUAL", "Importar Manualmente"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Aberto por", on_delete=models.SET_NULL, null=True)

    # Dados da NF
    nf_number = models.CharField(verbose_name="NF", max_length=50, blank=True, null=True)
    nf_key = models.CharField(max_length=44, verbose_name="Chave de Acesso", blank=False, null=False)
    supplier_name = models.CharField(verbose_name="Fornecedor", max_length=255, blank=True, null=True)
    supplier_cnpj = models.CharField(max_length=20, blank=True, null=True)

    # Progresso e Dados Brutos
    current_step = models.PositiveIntegerField(default=1)
    items_data = models.JSONField(default=list)
    payments_data = models.JSONField(default=list)
    method = models.CharField(verbose_name="Selecione o método de Importação de Itens", max_length=30, choices=ImportMethods.choices, default=ImportMethods.XML)
    status = models.CharField(max_length=20, choices=ImportStatus.choices, default=ImportStatus.DRAFT)

    class Meta:
        verbose_name = "Importação de Estoque"
        verbose_name_plural = "Importações de Estoque"

    def __str__(self):
        return f"Importação {self.nf_number} - {self.workshop}"

    @property
    def nf_number_display(self) -> str:
        from apps.stock.utils import extract_nf_number_from_access_key

        return str(self.nf_number or extract_nf_number_from_access_key(self.nf_key) or "---")

    @property
    def stockimport_status_badge(self):
        status_color = {
            StockImport.ImportStatus.DRAFT: "badge-soft badge-ghost",
            StockImport.ImportStatus.COMPLETED: "badge-success",
        }

        return {"text": self.get_status_display(), "class": status_color.get(self.status, "badge-ghost")}
