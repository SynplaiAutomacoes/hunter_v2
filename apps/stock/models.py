from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.conf import settings
from django.utils import timezone

from apps.core.infrastructure.models import TimeStampedModel
from apps.finance.models.payment_method import PaymentMethod
from apps.suppliers.models import Supplier
from djmoney.models.fields import MoneyField
from djmoney.money import Money


def _extract_nf_number_from_access_key(access_key: str | None) -> str:
    if not access_key:
        return ""
    normalized_key = "".join(character for character in str(access_key).strip() if character.isdigit())
    if len(normalized_key) == 44:
        return normalized_key[25:34].lstrip("0") or "0"
    return ""


class StockProduct(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="stock_products")
    product = models.OneToOneField("catalog.Product", on_delete=models.CASCADE, related_name="stock_products")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_products")
    current_quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("0"), verbose_name="Estoque Atual")
    minimum_quantity = models.IntegerField(default=0, verbose_name="Estoque Mínimo")
    restock_quantity = models.IntegerField(default=0, verbose_name="Estoque Reposição")
    last_nf = models.CharField(max_length=50, blank=True, null=True, verbose_name="Última NF")

    class Meta:
        verbose_name = "Produto do Estoque"
        verbose_name_plural = "Produtos do Estoque"

    def __str__(self):
        return f"{self.product.name} - {self.current_quantity} unidades"

    @property
    def unit_cost(self) -> Money:
        product = getattr(self, "product", None)
        cost_price = getattr(product, "cost_price", None)
        if isinstance(cost_price, Money):
            return cost_price
        return Money(Decimal(str(cost_price or 0)), "BRL")

    @property
    def item_total_cost(self) -> Money:
        return self.unit_cost * self.current_quantity

    @property
    def last_nf_display(self) -> str:
        return str(self.last_nf or "Nenhuma NF relacionada")


class StockMovement(TimeStampedModel):
    class MovementType(models.TextChoices):
        ENTRY = "ENTRADA", "Entrada"
        EXIT = "SAIDA", "Saída"

    class MovementStatus(models.TextChoices):
        WAITING = "AGUARDANDO", "Aguardando Aprovação"
        APPROVED = "APROVADO", "Aprovado"
        REJECTED = "REJEITADO", "Rejeitado"

    class MovementReason(models.TextChoices):
        STANDARD = "STANDARD", "Movimentação padrão"
        PURCHASE_RETURN = "PURCHASE_RETURN", "Saída por devolução de compra"
        TRANSPORT = "TRANSPORT", "Saída por Nota de Transporte"

    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="movements")
    stock_product = models.ForeignKey(StockProduct, on_delete=models.CASCADE, verbose_name="Peça", related_name="movements")
    stock_transfer = models.ForeignKey("stock.StockTransfer", on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")
    source_import_item = models.ForeignKey("stock.StockImportFiscalItem", on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movements", verbose_name="Item fiscal de origem")
    fiscal_document = models.ForeignKey("finance.FiscalDocument", on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movements", verbose_name="Documento fiscal")
    purchase_return_item = models.OneToOneField("finance.PurchaseReturnRequestItem", on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movement", verbose_name="Item da devolução de compra")
    transport_item = models.OneToOneField("finance.TransportRequestItem", on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movement", verbose_name="Item da Nota de Transporte")
    type = models.CharField(max_length=10, choices=MovementType.choices, verbose_name="Tipo")
    reason = models.CharField(max_length=24, choices=MovementReason.choices, default=MovementReason.STANDARD, db_index=True, verbose_name="Motivo")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, verbose_name="Fornecedor", null=True, blank=True, related_name="movements")
    transcation_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="movements", null=True)
    workorder = models.ForeignKey("workorder.WorkOrder", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    reversal_of = models.OneToOneField("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reversal_entry")
    quantity = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("1"), verbose_name="Quantidade")
    status = models.CharField(max_length=10, choices=MovementStatus.choices, verbose_name="Status", default=MovementStatus.WAITING)

    class Meta:
        verbose_name = "Movimentação de Estoque"
        verbose_name_plural = "Movimentações de Estoque"
        constraints = [
            models.UniqueConstraint(fields=["source_import_item"], condition=models.Q(type="ENTRADA"), name="unique_stock_entry_per_import_item"),
        ]

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

    @property
    def total_value(self):
        return self.stock_product.unit_cost * self.quantity

    @property
    def display_date(self):
        if self.type == self.MovementType.EXIT and self.workorder_id and self.workorder.delivered_at:
            return self.workorder.delivered_at
        return self.criado_em

    @property
    def workorder_reference(self):
        if self.workorder_id:
            budget_id = getattr(self.workorder, "budget_id", None)
            return f"OS #{budget_id}" if budget_id else f"OS (WO #{self.workorder_id})"
        return None


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
        return Money(self.first_installment_amount.amount + ((self.installments_count - 1) * self.remaining_installments_amount.amount), "BRL")


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
        return self.nf_number or _extract_nf_number_from_access_key(self.key)


class StockImport(TimeStampedModel):
    class ImportStatus(models.TextChoices):
        DRAFT = "RASCUNHO", "Rascunho"
        COMPLETED = "CONCLUIDO", "Concluído"

    class ImportMethods(models.TextChoices):
        SEFAZ = "SEFAZ", "SEFAZ"
        XML = "XML", "Arquivo XML"
        KEY = "KEY", "Chave de Acesso"
        MANUAL = "MANUAL", "Importar Manualmente"

    class FiscalValidationStatus(models.TextChoices):
        UNVALIDATED = "unvalidated", "Não validado"
        VALIDATED = "validated", "Validado"
        INVALID = "invalid", "Inválido"

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
    method = models.CharField(verbose_name="Método de importação", max_length=30, choices=ImportMethods.choices, default=ImportMethods.XML)
    xml_file_key = models.CharField(max_length=1024, blank=True, default="", db_index=True, verbose_name="XML no armazenamento")
    fiscal_document = models.OneToOneField("finance.FiscalDocument", on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_stock_import", verbose_name="Documento fiscal externo")
    fiscal_snapshot = models.JSONField(default=dict, blank=True, verbose_name="Snapshot fiscal normalizado")
    fiscal_issued_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Data de emissão fiscal")
    fiscal_validation_status = models.CharField(max_length=16, choices=FiscalValidationStatus.choices, default=FiscalValidationStatus.UNVALIDATED, db_index=True, verbose_name="Validação fiscal")
    fiscal_validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validado fiscalmente em")
    status = models.CharField(max_length=20, choices=ImportStatus.choices, default=ImportStatus.DRAFT)

    class Meta:
        verbose_name = "Importação de Estoque"
        verbose_name_plural = "Importações de Estoque"
        constraints = [
            models.UniqueConstraint(fields=["workshop", "nf_key"], condition=~models.Q(nf_key=""), name="unique_stock_import_access_key_per_workshop"),
        ]

    def __str__(self):
        return f"Importação {self.nf_number} - {self.workshop}"

    @property
    def nf_number_display(self) -> str:
        return self.nf_number or _extract_nf_number_from_access_key(self.nf_key)

    @property
    def stockimport_status_badge(self):
        status_color = {
            StockImport.ImportStatus.DRAFT: "badge-soft badge-ghost",
            StockImport.ImportStatus.COMPLETED: "badge-success",
        }

        return {"text": self.get_status_display(), "class": status_color.get(self.status, "badge-ghost")}


class StockImportFiscalItem(TimeStampedModel):
    stock_import = models.ForeignKey(StockImport, on_delete=models.PROTECT, related_name="fiscal_items", verbose_name="Importação de estoque")
    sequence = models.PositiveSmallIntegerField(verbose_name="Sequencial fiscal")
    stock_product = models.ForeignKey(StockProduct, on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_fiscal_items", verbose_name="Produto do estoque")
    product_code = models.CharField(max_length=120, blank=True, default="", verbose_name="Código do produto")
    description = models.CharField(max_length=255, verbose_name="Descrição")
    quantity = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.0001"))], verbose_name="Quantidade comprada")
    unit = models.CharField(max_length=12, blank=True, default="", verbose_name="Unidade")
    unit_value = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0"))], verbose_name="Valor unitário")
    total_value = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0"))], verbose_name="Valor total")
    ncm = models.CharField(max_length=10, blank=True, default="", verbose_name="NCM")
    cfop = models.CharField(max_length=8, blank=True, default="", verbose_name="CFOP")
    tax_snapshot = models.JSONField(default=dict, blank=True, verbose_name="Snapshot tributário")

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Item fiscal da importação de estoque"
        verbose_name_plural = "Itens fiscais da importação de estoque"
        constraints = [
            models.UniqueConstraint(fields=["stock_import", "sequence"], name="unique_fiscal_item_sequence_per_stock_import"),
        ]
        indexes = [
            models.Index(fields=["stock_import", "sequence"], name="stock_import_item_sequence_idx"),
            models.Index(fields=["stock_product"], name="stock_import_item_product_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.stock_product_id and self.stock_product.workshop_id != self.stock_import.workshop_id:
            raise ValidationError({"stock_product": "O produto de estoque pertence a outra oficina."})

    def __str__(self) -> str:
        return f"{self.stock_import.nf_number_display} item {self.sequence} - {self.description}"


class StockTransfer(TimeStampedModel):
    class TransferStatus(models.TextChoices):
        DRAFT = "RASCUNHO", "Rascunho"
        COMPLETED = "CONCLUIDO", "Concluído"

    class OperationType(models.TextChoices):
        TRANSFER = "TRANSFER", "Transferência entre oficinas"
        ADJUSTMENT = "ADJUSTMENT", "Baixa em estoque"

    operation_type = models.CharField(max_length=30, verbose_name="Tipo de operação", choices=OperationType.choices, default=OperationType.TRANSFER)
    reason = models.TextField(verbose_name="Motivo da Baixa", blank=True, null=True)
    source_workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina de Origem", on_delete=models.CASCADE, related_name="stock_transfers_sent", blank=True, null=True)
    destination_workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina de Destino", on_delete=models.CASCADE, related_name="stock_transfers_received", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Aberto por", on_delete=models.SET_NULL, null=True)
    current_step = models.PositiveIntegerField(default=1)
    items_data = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=TransferStatus.choices, default=TransferStatus.DRAFT)

    class Meta:
        verbose_name = "Transferência de Estoque"
        verbose_name_plural = "Transferências de Estoque"

    def __str__(self) -> str:
        if self.operation_type == StockTransfer.OperationType.TRANSFER:
            return f"Transferência {self.pk or '---'} - {self.source_workshop} -> {self.destination_workshop}"
        return "Baixa em Estoque"

    @property
    def stocktransfer_status_badge(self):
        status_color = {
            StockTransfer.TransferStatus.DRAFT: "badge-soft badge-ghost",
            StockTransfer.TransferStatus.COMPLETED: "badge-success",
        }

        return {"text": self.get_status_display(), "class": status_color.get(self.status, "badge-ghost")}
