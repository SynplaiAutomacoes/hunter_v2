from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.infrastructure.models import TimeStampedModel
from apps.finance.models.finance import NfeFreightMode


class PurchaseReturnRequestStatus(models.TextChoices):
    DRAFT = "draft", "Rascunho"
    READY = "ready", "Pronta para emissão"
    PROCESSING = "processing", "Em processamento"
    AUTHORIZED = "authorized", "Autorizada"
    REJECTED = "rejected", "Rejeitada"
    COMMUNICATION_ERROR = "communication_error", "Erro de comunicação"
    CONTINGENCY = "contingency", "Contingência"
    UNCERTAIN = "uncertain", "Aguardando reconciliação"
    CANCELED = "canceled", "Cancelada"


class PurchaseReturnStockStatus(models.TextChoices):
    WAITING_AUTHORIZATION = "waiting_authorization", "Aguardando autorização fiscal"
    PENDING = "pending", "Aguardando baixa"
    PROCESSED = "processed", "Estoque atualizado"
    ERROR = "error", "Erro na atualização do estoque"


class PurchaseReturnItemKind(models.TextChoices):
    STOCK = "stock", "Vinculado ao estoque"
    MANUAL = "manual", "Produto avulso"


class PurchaseReturnRequest(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="purchase_return_requests", verbose_name="Oficina")
    source_stock_import = models.ForeignKey("stock.StockImport", on_delete=models.PROTECT, related_name="purchase_return_requests", verbose_name="NF-e de compra")
    original_document = models.ForeignKey("finance.FiscalDocument", on_delete=models.PROTECT, related_name="purchase_return_requests", verbose_name="Documento fiscal original")
    fiscal_document = models.OneToOneField("finance.FiscalDocument", on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_return_request", verbose_name="Documento fiscal de devolução")
    requested_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_return_requests", verbose_name="Solicitante")
    current_step = models.PositiveSmallIntegerField(default=1, verbose_name="Etapa atual")
    status = models.CharField(max_length=24, choices=PurchaseReturnRequestStatus.choices, default=PurchaseReturnRequestStatus.DRAFT, db_index=True, verbose_name="Status")
    ready_at = models.DateTimeField(null=True, blank=True, verbose_name="Intenção criada em")
    operation_nature = models.CharField(max_length=255, default="Devolução de mercadoria", verbose_name="Natureza da operação")
    cfop = models.CharField(max_length=8, blank=True, default="", verbose_name="CFOP")
    tax_class = models.CharField(max_length=120, blank=True, default="", verbose_name="Classe de imposto")
    additional_information = models.TextField(blank=True, default="", verbose_name="Informações complementares")
    fisco_information = models.TextField(blank=True, default="", verbose_name="Informações ao fisco")
    volume = models.PositiveBigIntegerField(null=True, blank=True, verbose_name="Quantidade de volumes")
    freight_mode = models.PositiveSmallIntegerField(verbose_name="Modalidade de frete", choices=NfeFreightMode.choices, default=NfeFreightMode.NO_TRANSPORT)
    freight_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Frete")
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Desconto")
    accessory_expenses = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Despesas acessórias")
    insurance_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Seguro")
    customs_expenses = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Despesas aduaneiras")
    total_override = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Total informado")
    presence = models.CharField(max_length=1, blank=True, default="", verbose_name="Indicador de presença")
    intermediary = models.CharField(max_length=1, blank=True, default="", verbose_name="Indicador de intermediador")
    intermediary_cnpj = models.CharField(max_length=14, blank=True, default="", verbose_name="CNPJ do intermediador")
    intermediary_id = models.CharField(max_length=60, blank=True, default="", verbose_name="Identificador do intermediador")
    purchase_order = models.CharField(max_length=60, blank=True, default="", verbose_name="Pedido de compra")
    contract = models.CharField(max_length=60, blank=True, default="", verbose_name="Contrato")
    commitment_note = models.CharField(max_length=22, blank=True, default="", verbose_name="Nota de empenho")
    payment_indicator = models.CharField(max_length=1, blank=True, default="", verbose_name="Indicador de pagamento")
    payment_method = models.CharField(max_length=2, blank=True, default="", verbose_name="Meio de pagamento")
    payment_description = models.CharField(max_length=60, blank=True, default="", verbose_name="Descrição do pagamento")
    payment_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Valor do pagamento")
    payment_date = models.DateField(null=True, blank=True, verbose_name="Data do pagamento")
    issue_at = models.DateTimeField(null=True, blank=True, verbose_name="Data de emissão")
    departure_at = models.DateTimeField(null=True, blank=True, verbose_name="Data de entrada/saída")
    delivery_forecast = models.DateField(null=True, blank=True, verbose_name="Previsão de entrega")
    transport_snapshot = models.JSONField(default=dict, blank=True, verbose_name="Snapshot de transporte")
    supplier_ie = models.CharField(max_length=14, blank=True, null=True, verbose_name="Inscrição Estadual do fornecedor")
    FISCAL_CONFIGURATION_FIELDS: tuple[str, ...] = (
        "operation_nature",
        "cfop",
        "tax_class",
        "additional_information",
        "fisco_information",
        "volume",
        "freight_mode",
        "freight_amount",
        "discount_amount",
        "accessory_expenses",
        "insurance_amount",
        "customs_expenses",
        "total_override",
        "presence",
        "intermediary",
        "intermediary_cnpj",
        "intermediary_id",
        "purchase_order",
        "contract",
        "commitment_note",
        "payment_indicator",
        "payment_method",
        "payment_description",
        "payment_value",
        "payment_date",
        "issue_at",
        "departure_at",
        "delivery_forecast",
        "transport_snapshot",
        "supplier_ie",
    )
    stock_status = models.CharField(max_length=24, choices=PurchaseReturnStockStatus.choices, default=PurchaseReturnStockStatus.WAITING_AUTHORIZATION, db_index=True, verbose_name="Status do estoque")
    stock_processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Estoque atualizado em")
    stock_error = models.TextField(blank=True, default="", verbose_name="Erro de atualização do estoque")

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Intenção de devolução de compra"
        verbose_name_plural = "Intenções de devolução de compra"
        indexes = [
            models.Index(fields=["workshop", "status"], name="purchase_ret_workshop_idx"),
            models.Index(fields=["original_document", "status"], name="purchase_ret_document_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.source_stock_import_id and self.source_stock_import.workshop_id != self.workshop_id:
            errors["source_stock_import"] = "A NF-e de compra pertence a outra oficina."
        if self.original_document_id and self.original_document.workshop_id != self.workshop_id:
            errors["original_document"] = "O documento fiscal pertence a outra oficina."
        if self.source_stock_import_id and self.original_document_id and self.source_stock_import.fiscal_document_id != self.original_document_id:
            errors["original_document"] = "O documento fiscal não corresponde à importação de estoque."
        if self.fiscal_document_id and self.fiscal_document.workshop_id != self.workshop_id:
            errors["fiscal_document"] = "O documento fiscal de devolução pertence a outra oficina."
        if errors:
            raise ValidationError(errors)

    @property
    def resume_step(self) -> int:
        current = max(1, min(int(self.current_step or 1), 4))
        if self.status == PurchaseReturnRequestStatus.DRAFT:
            return min(current, 3)
        return 4

    @property
    def purchase_return_status_badge(self) -> dict[str, str]:
        status_color = {
            PurchaseReturnRequestStatus.DRAFT: "badge-soft badge-ghost",
            PurchaseReturnRequestStatus.READY: "badge-soft badge-info",
            PurchaseReturnRequestStatus.PROCESSING: "badge-soft badge-warning",
            PurchaseReturnRequestStatus.AUTHORIZED: "badge-success",
            PurchaseReturnRequestStatus.REJECTED: "badge-error",
            PurchaseReturnRequestStatus.COMMUNICATION_ERROR: "badge-error",
            PurchaseReturnRequestStatus.CONTINGENCY: "badge-soft badge-warning",
            PurchaseReturnRequestStatus.UNCERTAIN: "badge-warning",
            PurchaseReturnRequestStatus.CANCELED: "badge-soft badge-error",
        }
        return {
            "text": str(PurchaseReturnRequestStatus(self.status).label),
            "class": status_color.get(self.status, "badge-ghost"),
        }

    def __str__(self) -> str:
        return f"Devolução de compra {self.pk or '---'} - {self.source_stock_import.nf_number_display}"


class PurchaseReturnRequestItem(TimeStampedModel):
    request = models.ForeignKey(PurchaseReturnRequest, on_delete=models.CASCADE, related_name="items", verbose_name="Intenção de devolução")
    kind = models.CharField(max_length=12, choices=PurchaseReturnItemKind.choices, default=PurchaseReturnItemKind.STOCK, db_index=True, verbose_name="Tipo de item")
    source_item = models.ForeignKey("stock.StockImportFiscalItem", on_delete=models.PROTECT, null=True, blank=True, related_name="purchase_return_items", verbose_name="Item fiscal de origem")
    manual_snapshot = models.JSONField(default=dict, blank=True, verbose_name="Snapshot fiscal do produto avulso")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="Descrição")
    product_code = models.CharField(max_length=120, blank=True, default="", verbose_name="Código do produto")
    ncm = models.CharField(max_length=10, blank=True, default="", verbose_name="NCM")
    cest = models.CharField(max_length=10, blank=True, default="", verbose_name="CEST")
    unit = models.CharField(max_length=12, blank=True, default="", verbose_name="Unidade")
    cfop = models.CharField(max_length=8, blank=True, default="", verbose_name="CFOP")
    origin = models.PositiveSmallIntegerField(default=0, verbose_name="Origem tributária")
    tax_class = models.CharField(max_length=120, blank=True, default="", verbose_name="Classe de imposto")
    quantity = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.0001"))], verbose_name="Quantidade a devolver")
    unit_value = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0"))], verbose_name="Valor unitário")

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Item da intenção de devolução de compra"
        verbose_name_plural = "Itens da intenção de devolução de compra"
        constraints = [models.UniqueConstraint(fields=["request", "source_item"], condition=Q(source_item__isnull=False), name="unique_purchase_return_source_item")]

    def clean(self) -> None:
        super().clean()
        if self.request_id and self.source_item_id and self.source_item.stock_import_id != self.request.source_stock_import_id:
            raise ValidationError({"source_item": "O item fiscal não pertence à NF-e de compra selecionada."})
        if self.kind == PurchaseReturnItemKind.STOCK and self.source_item_id is None:
            raise ValidationError({"source_item": "Item vinculado ao estoque exige item fiscal de origem."})
        if self.kind == PurchaseReturnItemKind.MANUAL and self.source_item_id is not None:
            raise ValidationError({"source_item": "Produto avulso não pode possuir vínculo com estoque."})
        if self.kind == PurchaseReturnItemKind.MANUAL and not self.description:
            raise ValidationError({"description": "Produto avulso exige descrição."})

    @property
    def total_value(self) -> Decimal:
        return self.quantity * self.unit_value

    @property
    def display_description(self) -> str:
        if self.kind == PurchaseReturnItemKind.MANUAL:
            return self.description
        return self.source_item.description if self.source_item_id else self.description

    @property
    def display_unit(self) -> str:
        if self.kind == PurchaseReturnItemKind.MANUAL:
            return self.unit
        return self.source_item.unit if self.source_item_id else self.unit

    def __str__(self) -> str:
        return f"{self.display_description} - {self.quantity}"
