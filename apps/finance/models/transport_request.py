from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.infrastructure.models import TimeStampedModel


class TransportRequestStatus(models.TextChoices):
    DRAFT = "draft", "Rascunho"
    READY = "ready", "Pronta para emissão"
    PROCESSING = "processing", "Em processamento"
    AUTHORIZED = "authorized", "Autorizada"
    REJECTED = "rejected", "Rejeitada"
    COMMUNICATION_ERROR = "communication_error", "Erro de comunicação"
    CONTINGENCY = "contingency", "Contingência"
    UNCERTAIN = "uncertain", "Aguardando reconciliação"
    CANCELED = "canceled", "Cancelada"


class TransportStockStatus(models.TextChoices):
    WAITING_AUTHORIZATION = "waiting_authorization", "Aguardando autorização fiscal"
    PENDING = "pending", "Aguardando baixa"
    PROCESSED = "processed", "Estoque atualizado"
    ERROR = "error", "Erro na atualização do estoque"


class TransportRequest(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", on_delete=models.CASCADE, related_name="transport_requests", verbose_name="Oficina")
    source_stock_import = models.ForeignKey("stock.StockImport", on_delete=models.PROTECT, related_name="transport_requests", verbose_name="NF-e de entrada")
    original_document = models.ForeignKey("finance.FiscalDocument", on_delete=models.PROTECT, related_name="transport_requests", verbose_name="Documento fiscal original")
    fiscal_document = models.OneToOneField("finance.FiscalDocument", on_delete=models.PROTECT, null=True, blank=True, related_name="transport_request", verbose_name="Documento fiscal de transporte")
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT, null=True, blank=True, related_name="transport_requests", verbose_name="Destinatário")
    requested_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="transport_requests", verbose_name="Solicitante")
    current_step = models.PositiveSmallIntegerField(default=1, verbose_name="Etapa atual")
    status = models.CharField(max_length=24, choices=TransportRequestStatus.choices, default=TransportRequestStatus.DRAFT, db_index=True, verbose_name="Status")
    ready_at = models.DateTimeField(null=True, blank=True, verbose_name="Intenção criada em")
    operation_nature = models.CharField(max_length=255, default="Remessa para transporte", verbose_name="Natureza da operação")
    cfop = models.CharField(max_length=8, blank=True, default="", verbose_name="CFOP")
    tax_class = models.CharField(max_length=120, blank=True, default="", verbose_name="Classe de imposto")
    additional_information = models.TextField(blank=True, default="", verbose_name="Informações complementares")
    freight_mode = models.PositiveSmallIntegerField(default=3, verbose_name="Modalidade de frete")
    transport_snapshot = models.JSONField(default=dict, blank=True, verbose_name="Snapshot do transporte")
    stock_status = models.CharField(max_length=24, choices=TransportStockStatus.choices, default=TransportStockStatus.WAITING_AUTHORIZATION, db_index=True, verbose_name="Status do estoque")
    stock_processed_at = models.DateTimeField(null=True, blank=True, verbose_name="Estoque atualizado em")
    stock_error = models.TextField(blank=True, default="", verbose_name="Erro de atualização do estoque")

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Intenção de Nota de Transporte"
        verbose_name_plural = "Intenções de Nota de Transporte"
        permissions = [("issue_nfe_transport", "Pode emitir Nota de Transporte")]
        indexes = [
            models.Index(fields=["workshop", "status"], name="transport_req_workshop_idx"),
            models.Index(fields=["original_document", "status"], name="transport_req_document_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.source_stock_import_id and self.source_stock_import.workshop_id != self.workshop_id:
            errors["source_stock_import"] = "A NF-e de entrada pertence a outra oficina."
        if self.original_document_id and self.original_document.workshop_id != self.workshop_id:
            errors["original_document"] = "O documento fiscal pertence a outra oficina."
        if self.source_stock_import_id and self.original_document_id and self.source_stock_import.fiscal_document_id != self.original_document_id:
            errors["original_document"] = "O documento fiscal não corresponde à importação de estoque."
        if self.supplier_id and self.supplier.workshop_id != self.workshop_id:
            errors["supplier"] = "O destinatário pertence a outra oficina."
        if self.fiscal_document_id and self.fiscal_document.workshop_id != self.workshop_id:
            errors["fiscal_document"] = "O documento fiscal de transporte pertence a outra oficina."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"Nota de Transporte {self.pk or '---'} - {self.source_stock_import.nf_number_display}"


class TransportRequestItem(TimeStampedModel):
    request = models.ForeignKey(TransportRequest, on_delete=models.CASCADE, related_name="items", verbose_name="Intenção de transporte")
    source_item = models.ForeignKey("stock.StockImportFiscalItem", on_delete=models.PROTECT, related_name="transport_request_items", verbose_name="Item fiscal de origem")
    quantity = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.0001"))], verbose_name="Quantidade a transportar")
    unit_value = models.DecimalField(max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0"))], verbose_name="Valor unitário")

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Item da intenção de transporte"
        verbose_name_plural = "Itens da intenção de transporte"
        constraints = [models.UniqueConstraint(fields=["request", "source_item"], name="unique_transport_request_source_item")]

    def clean(self) -> None:
        super().clean()
        if self.request_id and self.source_item_id and self.source_item.stock_import_id != self.request.source_stock_import_id:
            raise ValidationError({"source_item": "O item fiscal não pertence à NF-e de entrada selecionada."})

    @property
    def total_value(self) -> Decimal:
        return self.quantity * self.unit_value

    def __str__(self) -> str:
        return f"{self.source_item.description} - {self.quantity}"
