from __future__ import annotations

import re
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from djmoney.models.fields import MoneyField
import stdnum.ean


from apps.core.models import TimeStampedModel
from apps.stock.models import StockProduct
from apps.workshops.models.workshops import Workshop
from apps.catalog.models.groups import CatalogGroup


def validate_ean(value):
    if value and not stdnum.ean.is_valid(value):
        raise ValidationError("Código de Barras (EAN) inválido.")


def validate_ncm(value):
    clean_value = value.replace(".", "")
    if clean_value:
        if not re.match(r"^\d{8}$", clean_value):
            raise ValidationError("NCM inválido. O código deve conter 8 dígitos numéricos.")


class Product(TimeStampedModel):
    class Unit(models.TextChoices):
        UND = "UND", "UND"
        PC = "PC", "PC"
        JG = "JG", "JG"
        GR = "GR", "GR"
        LT = "LT", "LT"
        KG = "KG", "KG"
        BIS = "BIS", "BIS"
        CX = "CX", "CX"
        KIT = "KIT", "KIT"
        TB = "TB", "TB"

    class OriginCST(models.IntegerChoices):
        NACIONAL = 0, "0 - Nacional"
        ESTRANGEIRA_IMPORTACAO_DIRETA = 1, "1 - Estrangeira (Importação direta)"
        ESTRANGEIRA_ADQUIRIDA_MERCADO_INTERNO = 2, "2 - Estrangeira (Adq. mercado interno)"
        NACIONAL_MER_SUPERIOR_40 = 3, "3 - Nacional (Conteúdo Importação > 40%)"
        NACIONAL_PRODUCAO_BASICA = 4, "4 - Nacional (Produção conforme PPB)"
        NACIONAL_MENOR_40 = 5, "5 - Nacional (Conteúdo Importação <= 40%)"
        ESTRANGEIRA_SEM_SIMILAR = 6, "6 - Estrangeira (Importação direta, sem similar)"
        ESTRANGEIRA_ADQUIRIDA_INTERNO_SEM_SIMILAR = 7, "7 - Estrangeira (Adq. interno, sem similar)"
        NACIONAL_SUPERIOR_70 = 8, "8 - Nacional (Conteúdo Importação > 70%)"

    class Purpose(models.TextChoices):
        RESALE = "REVENDA", "Revenda / Aplicação"
        CONSUMPTION = "CONSUMO", "Consumo Interno / Uso e Consumo"
        ASSET = "ATIVO", "Ativo Imobilizado"

    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="products",
    )

    # --- Dados de Identificação ---
    code = models.CharField(verbose_name="Código", max_length=50)
    name = models.CharField(verbose_name="Produto", max_length=255)
    description = models.CharField(verbose_name="Descrição", max_length=255, blank=True)
    unit = models.CharField(verbose_name="Unidade", max_length=5, choices=Unit.choices)

    group = models.ForeignKey(CatalogGroup, verbose_name="Grupo", on_delete=models.CASCADE, related_name="products")
    brand = models.CharField(verbose_name="Marca", max_length=100, blank=True)
    model = models.CharField(verbose_name="Modelo", max_length=100, blank=True)

    # --- Estoque e Localização ---
    sku = models.CharField(verbose_name="SKU", max_length=50, blank=True)
    barcode = models.CharField(verbose_name="Código de Barras", max_length=14, blank=True, validators=[validate_ean], help_text="EAN-13 ou EAN-8")
    location = models.CharField(verbose_name="Localização", max_length=100, blank=True)

    # --- Relacionamentos ---
    # ManyToMany com 'self' permite relacionar produtos entre si
    equivalent_parts = models.ManyToManyField("self", verbose_name="Peças Equivalentes", blank=True, symmetrical=True)

    # --- Financeiro ---
    cost_price = MoneyField(verbose_name="Valor de Custo", max_digits=14, decimal_places=2)
    selling_price = MoneyField(verbose_name="Valor de Venda", max_digits=14, decimal_places=2)
    last_used_price = MoneyField(verbose_name="Ultimo Valor Utilizado", max_digits=14, decimal_places=2, null=True, blank=True)

    # Margem armazenada para facilidade de consulta, mas calculada no form
    profit_margin = models.DecimalField(verbose_name="Margem de Lucro", max_digits=7, decimal_places=2, default=0, blank=True)

    # --- Fiscal ---
    ncm = models.CharField(verbose_name="NCM", max_length=10, validators=[validate_ncm], blank=True)
    cest = models.CharField(verbose_name="CEST", max_length=10, blank=True)
    origin_cst = models.IntegerField(verbose_name="Origem CST A", choices=OriginCST.choices, default=OriginCST.NACIONAL)
    purpose = models.CharField(verbose_name="Finalidade", max_length=20, choices=Purpose.choices, default=Purpose.RESALE)

    # --- Detalhes ---
    image = models.ImageField(verbose_name="Imagem", upload_to="products/", blank=True, null=True)
    application = models.TextField(verbose_name="Aplicação", blank=True)

    is_active = models.BooleanField(verbose_name="Ativo", default=True)

    @property
    def current_stock(self):
        stock = getattr(self, "stock_products", None)
        return stock.current_quantity if stock else 0

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        constraints = [
            models.UniqueConstraint(
                fields=("workshop", "code"),
                name="unique_product_code_per_workshop",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


@receiver(post_save, sender=Product)
def create_stock_product(sender, instance, created, **kwargs):
    if created:
        StockProduct.objects.get_or_create(workshop=instance.workshop, product=instance)
