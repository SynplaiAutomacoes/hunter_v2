import logging

from django.db import models

from apps.core.models import TimeStampedModel


logger = logging.getLogger(__name__)


class BatchStatus(models.TextChoices):
    processando = "processando"
    processado = "processado"
    agendado = "agendado"
    reprovado = "reprovado"
    cancelado = "cancelado"
    contingencia = "contingencia"


class NfseItemStatus(models.TextChoices):
    processando = "processando"
    aprovado = "aprovado"
    agendado = "agendado"
    reprovado = "reprovado"
    cancelado = "cancelado"
    contingencia = "contingencia"


class NfsePdfStatus(models.TextChoices):
    processando = "processando"
    processado = "processado"
    indisponivel = "indisponivel"


class NfseRequestStatus(models.TextChoices):
    WAITING_WO = "waiting_wo", "Aguardando Ordem de Serviço"
    CHECKING_CLIENT = "checking_client", "Verificando Cliente"
    CHECKING_SERVICES = "checking_services", "Verificando Serviços"
    PROCESSING = "processing", "Processando"
    APPROVED = "approved", "Aprovado"
    REPROVED = "reproved", "Reprovado"
    SCHEDULED = "scheduled", "Agendado"
    CANCELED = "canceled", "Cancelado"
    CONTINGENCY = "contingency", "Contingência"


class TaxClassNfe(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="tax_classes_nfe")
    reference = models.CharField(verbose_name="Referência", max_length=30)
    description = models.CharField(verbose_name="Descrição", max_length=255, blank=True, default="")
    status = models.CharField(verbose_name="Status", max_length=30, blank=True, default="")
    remote_date = models.CharField(verbose_name="Data", max_length=40, blank=True, default="")
    remote_updated_date = models.CharField(verbose_name="Data de atualização remota", max_length=40, blank=True, default="")
    informacoes_fisco = models.TextField(verbose_name="Informações ao Fisco", blank=True, default="")
    informacoes_complementares = models.TextField(verbose_name="Informações complementares", blank=True, default="")
    icms = models.JSONField(verbose_name="Cenários ICMS", blank=True, default=list)
    ipi = models.JSONField(verbose_name="Cenários IPI", blank=True, default=list)
    pis = models.JSONField(verbose_name="Cenários PIS", blank=True, default=list)
    cofins = models.JSONField(verbose_name="Cenários COFINS", blank=True, default=list)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "reference"], name="unique_tax_class_nfe_per_workshop_reference"),
        ]
        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]

    def __str__(self) -> str:
        workshop_id = getattr(self, "workshop_id", "-")
        return f"NF-e {self.reference} ({workshop_id})"


class TaxClassNfse(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="tax_classes_nfse")
    reference = models.CharField(verbose_name="Referência", max_length=30)
    description = models.CharField(verbose_name="Descrição", max_length=255, blank=True, default="")
    status = models.CharField(verbose_name="Status", max_length=30, blank=True, default="")
    remote_date = models.CharField(verbose_name="Data", max_length=40, blank=True, default="")
    remote_updated_date = models.CharField(verbose_name="Data de atualização remota", max_length=40, blank=True, default="")
    informacoes_fisco = models.TextField(verbose_name="Informações ao Fisco", blank=True, default="")
    informacoes_complementares = models.TextField(verbose_name="Informações complementares", blank=True, default="")

    tipo_emissao = models.CharField(verbose_name="Tipo de emissão", max_length=10, blank=True, default="")
    codigo_servico = models.CharField(verbose_name="Código do serviço", max_length=20, blank=True, default="")
    codigo_tributacao_municipio = models.CharField(verbose_name="Código tributação município", max_length=20, blank=True, default="")
    tributacao_iss = models.CharField(verbose_name="Tributação ISS", max_length=10, blank=True, default="")
    tipo_imunidade = models.CharField(verbose_name="Tipo imunidade", max_length=10, blank=True, default="")
    retencao_iss = models.CharField(verbose_name="Retenção ISS", max_length=10, blank=True, default="")
    cst_pis_cofins = models.CharField(verbose_name="CST PIS/COFINS", max_length=10, blank=True, default="")
    retencao_pis_cofins = models.CharField(verbose_name="Retenção PIS/COFINS", max_length=10, blank=True, default="")
    natureza_operacao = models.CharField(verbose_name="Natureza da operação", max_length=10, blank=True, default="")
    exigibilidade_iss = models.CharField(verbose_name="Exigibilidade ISS", max_length=10, blank=True, default="")
    iss_retido = models.CharField(verbose_name="ISS retido", max_length=10, blank=True, default="")
    responsavel_retencao = models.CharField(verbose_name="Responsável retenção", max_length=10, blank=True, default="")
    codigo_cnae = models.CharField(verbose_name="Código CNAE", max_length=20, blank=True, default="")

    iss = models.DecimalField(verbose_name="Alíquota ISS", max_digits=7, decimal_places=2, null=True, blank=True)
    pis = models.DecimalField(verbose_name="Alíquota PIS", max_digits=7, decimal_places=2, null=True, blank=True)
    cofins = models.DecimalField(verbose_name="Alíquota COFINS", max_digits=7, decimal_places=2, null=True, blank=True)
    inss = models.DecimalField(verbose_name="Alíquota INSS", max_digits=7, decimal_places=2, null=True, blank=True)
    ir = models.DecimalField(verbose_name="Alíquota IR", max_digits=7, decimal_places=2, null=True, blank=True)
    csll = models.DecimalField(verbose_name="Alíquota CSLL", max_digits=7, decimal_places=2, null=True, blank=True)

    ibs_situacao_tributaria = models.CharField(verbose_name="IBS/CBS Situação tributária", max_length=30, blank=True, default="")
    ibs_classificacao_tributaria = models.CharField(verbose_name="IBS/CBS Classificação tributária", max_length=30, blank=True, default="")
    ibs_situacao_tributaria_regular = models.CharField(verbose_name="IBS/CBS Situação regular", max_length=30, blank=True, default="")
    ibs_classificacao_tributaria_regular = models.CharField(verbose_name="IBS/CBS Classificação regular", max_length=30, blank=True, default="")
    ibs_credito_presumido = models.CharField(verbose_name="IBS/CBS Crédito presumido", max_length=30, blank=True, default="")
    ibs_aliquota_diferimento_estadual = models.DecimalField(verbose_name="IBS estadual diferimento", max_digits=7, decimal_places=2, null=True, blank=True)
    ibs_aliquota_diferimento_municipal = models.DecimalField(verbose_name="IBS municipal diferimento", max_digits=7, decimal_places=2, null=True, blank=True)
    cbs_aliquota_diferimento = models.DecimalField(verbose_name="CBS diferimento", max_digits=7, decimal_places=2, null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "reference"], name="unique_tax_class_nfse_per_workshop_reference"),
        ]
        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]

    def __str__(self) -> str:
        workshop_id = getattr(self, "workshop_id", "-")
        return f"NFS-e {self.reference} ({workshop_id})"


class TaxClassSyncState(TimeStampedModel):
    workshop = models.OneToOneField("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="tax_class_sync_state")
    synced_once = models.BooleanField(verbose_name="Sincronização inicial concluída", default=False)

    def __str__(self) -> str:
        state = "ok" if self.synced_once else "pending"
        workshop_id = getattr(self, "workshop_id", "-")
        return f"TaxClassSyncState[{state}] ({workshop_id})"


class NfseRequest(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE)
    current_step = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=NfseRequestStatus.choices, default=NfseRequestStatus.WAITING_WO)
    service_description = models.TextField(verbose_name="Discriminação do Serviço", blank=True, default="")
    tax_class = models.CharField(verbose_name="Classe de Imposto", max_length=30, default="REF000000")

    def set_status(self, status: NfseRequestStatus):
        self.status = status
        self.save(update_fields=["status"])

    @property
    def customer_name(self) -> str:
        customer = getattr(getattr(self.workorder, "budget", None), "customer", None)
        if not customer:
            return "-"
        return customer.name

    @property
    def nfse_request_status_badge(self) -> dict[str, str]:
        status_color = {
            NfseRequestStatus.WAITING_WO: "badge-soft badge-ghost",
            NfseRequestStatus.CHECKING_CLIENT: "badge-soft badge-info",
            NfseRequestStatus.CHECKING_SERVICES: "badge-soft badge-info",
            NfseRequestStatus.PROCESSING: "badge-soft badge-warning",
            NfseRequestStatus.APPROVED: "badge-success",
            NfseRequestStatus.REPROVED: "badge-error",
            NfseRequestStatus.SCHEDULED: "badge-soft badge-warning",
            NfseRequestStatus.CANCELED: "badge-soft badge-error",
            NfseRequestStatus.CONTINGENCY: "badge-soft badge-warning",
        }

        return {
            "text": str(NfseRequestStatus(self.status).label),
            "class": status_color.get(self.status, "badge-ghost"),
        }

    def update_status_based_on_request(self, request_status: str | None) -> bool:
        if not request_status:
            return False

        normalized_status = str(request_status).strip().lower()
        status_mapping = {
            "processando": NfseRequestStatus.PROCESSING,
            "processado": NfseRequestStatus.APPROVED,
            "aprovado": NfseRequestStatus.APPROVED,
            "reprovado": NfseRequestStatus.REPROVED,
            "agendado": NfseRequestStatus.SCHEDULED,
            "cancelado": NfseRequestStatus.CANCELED,
            "contingencia": NfseRequestStatus.CONTINGENCY,
        }
        mapped_status = status_mapping.get(normalized_status)
        if not mapped_status:
            logger.warning("Status desconhecido recebido no webhook de NFS-e", extra={"request_status": request_status})
            return False

        self.set_status(mapped_status)
        return True

    def __str__(self):
        workorder_pk = getattr(self, "workorder_id", None) or "-"
        return f"NFS-e Request #{self.pk} - OS #{workorder_pk}"


class NfseBatch(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE)
    request = models.ForeignKey(NfseRequest, verbose_name="Requisição de NFS-e", related_name="batches", on_delete=models.SET_NULL, null=True)
    uuid = models.UUIDField(db_index=True)  # UUID do lote
    model = models.CharField(max_length=255, default="lote_rps")
    status = models.CharField(max_length=20, choices=BatchStatus.choices, default=BatchStatus.processando)
    reason = models.TextField(blank=True, default="")
    batch_number = models.CharField(max_length=40, blank=True, default="")  # Número do lote
    batch_series = models.CharField(max_length=20, blank=True, default="")  # Série do lote
    rps_quantity = models.PositiveIntegerField(default=0)
    protocol = models.CharField(max_length=60, blank=True, default="")
    log_payload = models.JSONField(blank=True, default=dict)
    raw_payload = models.JSONField(blank=True, default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workorder", "uuid"], name="unique_nfse_batch_per_workorder"),
        ]

        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]


class NfseItem(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE)
    request = models.ForeignKey(NfseRequest, verbose_name="Requisição de NFS-e", related_name="items", on_delete=models.SET_NULL, null=True)
    batch = models.ForeignKey(NfseBatch, verbose_name="Lote", related_name="items", on_delete=models.SET_NULL, null=True)
    uuid = models.UUIDField(db_index=True)  # UUID da NFS-e
    model = models.CharField(max_length=255, default="nfse")
    status = models.CharField(max_length=20, choices=NfseItemStatus.choices, default=NfseItemStatus.processando)
    reason = models.TextField(blank=True, default="")
    number = models.CharField(max_length=40, blank=True, default="")  # Número da NFS-e
    verification_code = models.CharField(max_length=60, blank=True, default="")
    rps_series = models.CharField(max_length=20, blank=True, default="")  # Série do RPS
    rps_number = models.CharField(max_length=40, blank=True, default="")  # Número do RPS
    xml_url = models.URLField(blank=True, default="")
    pdf_nfse_url = models.URLField(blank=True, default="")
    pdf_nfse_status = models.CharField(max_length=20, choices=NfsePdfStatus.choices, default=NfsePdfStatus.processando)
    pdf_rps_url = models.URLField(blank=True, default="")
    log_payload = models.JSONField(blank=True, default=dict)
    raw_payload = models.JSONField(blank=True, default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workorder", "uuid"], name="unique_nfse_item_per_workorder"),
        ]

        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]
