from django.db import models
from django.conf import settings

from apps.catalog.models.products import Product
from apps.core.models import TimeStampedModel
from apps.suppliers.models import Supplier


class StockProduct(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="stock_products")
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="stock_products")
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
    stock_product = models.ForeignKey(StockProduct, on_delete=models.CASCADE, related_name="movements")
    type = models.CharField(max_length=10, choices=MovementType.choices, verbose_name="Tipo de Movimentação")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")
    transcation_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="movements", null=True)
    quantity = models.IntegerField(default=1, verbose_name="Quantidade")
    status = models.CharField(max_length=10, choices=MovementStatus.choices, verbose_name="Status")