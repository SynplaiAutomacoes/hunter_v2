from django.db import models
from django.conf import settings

from apps.core.models import TimeStampedModel
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
    stock_product = models.ForeignKey(StockProduct, on_delete=models.CASCADE, verbose_name="Peça",related_name="movements")
    type = models.CharField(max_length=10, choices=MovementType.choices, verbose_name="Tipo")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, verbose_name="Fornecedor", null=True, blank=True, related_name="movements")
    transcation_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="movements", null=True)
    quantity = models.IntegerField(default=1, verbose_name="Quantidade")
    status = models.CharField(max_length=10, choices=MovementStatus.choices, verbose_name="Status", default=MovementStatus.WAITING)

    @property
    def get_product_reference(self):
        return self.stock_product.product

    @property
    def location(self):
        return self.stock_product.product.location


class StockPaymentMethod(TimeStampedModel):
    PAYMENT_METHOD_CHOICES = (
        ("CREDITO", "Cartão de Crédito"),
        ("DEBITO", "Cartão de Débito"),
        ("PIX", "Pix"),
        ("DINHEIRO", "Dinheiro"),
        ("BOLETO", "Boleto"),
        ("TRANSFERENCIA", "Transferência/TED"),
    )

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="stockpayments")
    payment_method = models.CharField(verbose_name="Forma de Pagamento", choices=PAYMENT_METHOD_CHOICES, max_length=20)
    installments_count = models.PositiveIntegerField(verbose_name="Número de Parcelas", default=1)
    first_installment_amount = MoneyField(verbose_name="Valor da primeira parcela", max_digits=14, decimal_places=2, default=0.00)
    remaining_installments_amount = MoneyField(verbose_name="Valor das parcelas restantes", max_digits=14, decimal_places=2, default=0.00)
    nf_number = models.CharField(max_length=60, verbose_name="Número da NF", null=False, blank=False)

    @property
    def total_paid(self):
        return self.first_installment_amount.amount + ((self.installments_count - 1) * self.remaining_installments_amount.amount)


class SefazZipCache(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="sefaz_caches")
    key = models.CharField(max_length=44, unique=True, verbose_name="Chave de Acesso")
    nf_number = models.CharField(max_length=20, null=True, blank=True)
    issue_date = models.DateTimeField(null=True, blank=True)
    issuer_name = models.CharField(max_length=255, null=True, blank=True)
    issuer_cnpj = models.CharField(max_length=20, null=True, blank=True)
    total_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    is_imported = models.BooleanField(default=False)
    xml_archive = models.TextField(null=True, blank=True)
