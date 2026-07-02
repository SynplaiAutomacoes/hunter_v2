import logging
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.finance.services.webmania_status import normalize_nfe_request_status, normalize_nfse_request_status


logger = logging.getLogger(__name__)


def _default_pricing_slider_from_workorder(*, workorder_id: int | None, workorder: object | None) -> int | None:
    if workorder is None and workorder_id is None:
        return None

    resolved_workorder = workorder
    if resolved_workorder is None:
        from apps.workorder.models import WorkOrder

        resolved_workorder = WorkOrder.objects.select_related("budget").filter(pk=workorder_id).first()
        if resolved_workorder is None:
            return None

    budget = getattr(resolved_workorder, "budget", None)
    if budget is None:
        return None

    return int(getattr(budget, "slider", 0) or 0)


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
    substituido = "substituido"


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


class NfeItemStatus(models.TextChoices):
    processando = "processando"
    aprovado = "aprovado"
    reprovado = "reprovado"
    cancelado = "cancelado"
    denegado = "denegado"
    contingencia = "contingencia"


class NfeRequestStatus(models.TextChoices):
    WAITING_WO = "waiting_wo", "Aguardando Ordem de Serviço"
    CHECKING_CLIENT = "checking_client", "Verificando Cliente"
    CHECKING_PRODUCTS = "checking_products", "Verificando Produtos"
    PROCESSING = "processing", "Processando"
    APPROVED = "approved", "Aprovado"
    REPROVED = "reproved", "Reprovado"
    DENIED = "denied", "Denegado"
    CANCELED = "canceled", "Cancelado"
    CONTINGENCY = "contingency", "Contingência"
    INVALIDATED = "invalidated", "Inutilizada"


class FiscalEmissionAttemptStatus(models.TextChoices):
    STARTED = "started", "Iniciada"
    SENT = "sent", "Enviada"
    SUCCEEDED = "succeeded", "Concluida"
    FAILED = "failed", "Falhou"
    UNCERTAIN = "uncertain", "Incerta"


class FiscalEmissionDocumentKind(models.TextChoices):
    NFE = "nfe", "NF-e"
    NFCE = "nfce", "NFC-e"
    NFSE = "nfse", "NFS-e"


class FiscalEmissionOperationType(models.TextChoices):
    EMISSION = "emission", "Emissao"
    CCE = "cce", "Carta de correcao"
    RETURN = "return", "Devolucao"
    REVERSAL = "reversal", "Estorno"
    COMPLEMENTARY_PRICE_QUANTITY = "complementary_price_quantity", "Complementar preco/quantidade"
    ADJUSTMENT = "adjustment", "Ajuste"
    NFCE_EMISSION = "nfce_emission", "Emissao NFC-e"
    NFCE_CANCELLATION = "nfce_cancellation", "Cancelamento NFC-e"
    NFCE_INUTILIZATION = "nfce_inutilization", "Inutilizacao NFC-e"
    NFE_IBS_CBS_EVENT = "nfe_ibs_cbs_event", "Evento IBS/CBS"
    NFE_IBS_CBS_EVENT_CANCELLATION = "nfe_ibs_cbs_event_cancellation", "Cancelamento de evento IBS/CBS"
    NFE_CREDIT_EMISSION = "nfe_credit_emission", "Emissao NF-e de credito"
    NFE_CREDIT_CANCELLATION = "nfe_credit_cancellation", "Cancelamento NF-e de credito"
    NFE_DEBIT_EMISSION = "nfe_debit_emission", "Emissao NF-e de debito"
    NFE_DEBIT_CANCELLATION = "nfe_debit_cancellation", "Cancelamento NF-e de debito"
    NFSE_CANCELLATION = "nfse_cancellation", "Cancelamento NFS-e"
    NFSE_SUBSTITUTION = "nfse_substitution", "Substituicao NFS-e"
    NFSE_MANIFESTATION = "nfse_manifestation", "Manifestacao NFS-e"
    NFSE_MANUAL_EMISSION = "nfse_manual_emission", "Emissao manual NFS-e"


class FiscalDocumentType(models.TextChoices):
    NFE = "nfe", "NF-e"
    NFCE = "nfce", "NFC-e"


class FiscalDocumentStatus(models.TextChoices):
    PROCESSING = "processando", "Processando"
    APPROVED = "aprovado", "Aprovado"
    REPROVED = "reprovado", "Reprovado"
    CANCELED = "cancelado", "Cancelado"
    DENIED = "denegado", "Denegado"
    CONTINGENCY = "contingencia", "Contingencia"
    UNCERTAIN = "uncertain", "Incerto"


class FiscalDocumentOrigin(models.TextChoices):
    LOCAL = "local", "Local"
    EXTERNAL = "external", "Externo"
    DERIVED = "derived", "Derivado"
    MANUAL = "manual", "Manual"


class FiscalDocumentPurpose(models.TextChoices):
    NORMAL = "normal", "Normal"
    RETURN = "return", "Devolucao"
    REVERSAL = "reversal", "Estorno"
    COMPLEMENTARY = "complementary", "Complementar"
    ADJUSTMENT = "adjustment", "Ajuste"
    CREDIT = "credit", "Credito"
    DEBIT = "debit", "Debito"


class FiscalDocumentComplementaryType(models.TextChoices):
    PRICE_QUANTITY = "price_quantity", "Preco/quantidade"


class FiscalDocumentLinkRole(models.TextChoices):
    RETURNS = "returns", "Devolve"
    REVERSES = "reverses", "Estorna"
    COMPLEMENTS = "complements", "Complementa"
    ADJUSTS = "adjusts", "Ajusta"
    CREDITS = "credits", "Credita"
    DEBITS = "debits", "Debita"


class FiscalDocumentEventType(models.TextChoices):
    CCE = "cce", "Carta de correcao"
    CANCELLATION = "cancellation", "Cancelamento"
    IBS_CBS = "ibs_cbs", "Evento IBS/CBS"
    IBS_CBS_CANCELLATION = "ibs_cbs_cancellation", "Cancelamento de evento IBS/CBS"


class FiscalDocumentEventStatus(models.TextChoices):
    STARTED = "started", "Iniciado"
    SENT = "sent", "Enviado"
    SUCCEEDED = "succeeded", "Concluido"
    PROCESSING = "processando", "Processando"
    APPROVED = "aprovado", "Aprovado"
    REPROVED = "reprovado", "Reprovado"
    CANCELED = "cancelado", "Cancelado"
    FAILED = "failed", "Falhou"
    UNCERTAIN = "uncertain", "Incerto"


class FiscalNumberInutilizationStatus(models.TextChoices):
    STARTED = "started", "Iniciada"
    SENT = "sent", "Enviada"
    SUCCEEDED = "succeeded", "Concluida"
    FAILED = "failed", "Falhou"
    UNCERTAIN = "uncertain", "Incerta"


class FiscalReferencedBasisStatus(models.TextChoices):
    DRAFT = "draft", "Rascunho"
    READY = "ready", "Pronta para aprovacao"
    APPROVED = "approved", "Aprovada"
    REJECTED = "rejected", "Rejeitada"
    INVALID = "invalid", "Invalida"
    ARCHIVED = "archived", "Arquivada"


class FiscalReferencedBasisType(models.TextChoices):
    CREDIT = "credit", "Credito"
    DEBIT = "debit", "Debito"


class FiscalProductPreviewStatus(models.TextChoices):
    DRAFT = "draft", "Rascunho"
    VALIDATED = "validated", "Validada"
    APPROVED = "approved", "Aprovada"
    INVALID = "invalid", "Invalida"


class FiscalHypothesis(models.TextChoices):
    CREDIT_FINE_INTEREST = "credit_fine_interest", "Credito - multa/juros"
    CREDIT_ZFM_PRESUMED = "credit_zfm_presumed", "Credito - presumido ZFM"
    CREDIT_REFUSAL = "credit_refusal", "Credito - recusa/nao localizacao"
    CREDIT_VALUE_REDUCTION = "credit_value_reduction", "Credito - reducao de valores"
    CREDIT_SUCCESSION = "credit_succession", "Credito - sucessao"
    DEBIT_COOPERATIVE = "debit_cooperative", "Debito - cooperativas"
    DEBIT_EXEMPT_OUTPUT = "debit_exempt_output", "Debito - saidas imunes/isentas"
    DEBIT_UNPROCESSED_INVOICE = "debit_unprocessed_invoice", "Debito - NF nao processada"
    DEBIT_FINE_INTEREST = "debit_fine_interest", "Debito - multa/juros"
    DEBIT_SUCCESSION = "debit_succession", "Debito - sucessao"
    DEBIT_ADVANCE_PAYMENT = "debit_advance_payment", "Debito - pagamento antecipado"
    DEBIT_STOCK_LOSS = "debit_stock_loss", "Debito - perda de estoque"
    DEBIT_SN_EXCLUSION = "debit_sn_exclusion", "Debito - desenquadramento do SN"


class TaxClassNfe(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="tax_classes_nfe")
    reference = models.CharField(verbose_name="Referência", max_length=30)
    description = models.CharField(verbose_name="Descrição", max_length=255, blank=True, default="")
    status = models.CharField(verbose_name="Status", max_length=30, blank=True, default="")
    remote_date = models.CharField(verbose_name="Data", max_length=40, blank=True, default="")
    remote_updated_date = models.CharField(verbose_name="Data de atualização remota", max_length=40, blank=True, default="")
    informacoes_fisco = models.TextField(verbose_name="Informações ao Fisco", blank=True, default="")
    informacoes_complementares = models.TextField(verbose_name="Informações complementares", blank=True, default="")
    ibs_cbs_enabled = models.BooleanField(verbose_name="IBS/CBS habilitado", default=False)
    ibs_cbs_situacao_tributaria = models.CharField(verbose_name="IBS/CBS Situação tributária", max_length=3, blank=True, default="")
    ibs_cbs_classificacao_tributaria = models.CharField(verbose_name="IBS/CBS Classificação tributária", max_length=6, blank=True, default="")
    ibs_cbs_situacao_tributaria_regular = models.CharField(verbose_name="IBS/CBS Situação regular", max_length=3, blank=True, default="")
    ibs_cbs_classificacao_tributaria_regular = models.CharField(verbose_name="IBS/CBS Classificação regular", max_length=6, blank=True, default="")
    ibs_cbs_details = models.JSONField(verbose_name="IBS/CBS detalhes", blank=True, default=dict)
    ibs_cbs_configured_by = models.ForeignKey("accounts.User", verbose_name="IBS/CBS configurado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="configured_nfe_tax_classes_ibs_cbs")
    ibs_cbs_configured_at = models.DateTimeField(verbose_name="IBS/CBS configurado em", null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "reference"], name="unique_tax_class_nfe_per_workshop_reference"),
        ]
        indexes = [
            models.Index(fields=["workshop", "status"]),
            models.Index(fields=["workshop", "ibs_cbs_enabled"]),
        ]
        permissions = [
            ("manage_ibs_cbs_tax_classes", "Pode configurar IBS/CBS em classes fiscais"),
            ("view_ibs_cbs_configuration", "Pode visualizar configuracao IBS/CBS"),
        ]

    def __str__(self) -> str:
        workshop_id = getattr(self, "workshop_id", "-")
        return f"Nota Fiscal {self.reference} ({workshop_id})"


class TaxClassNfeIcmsScenario(models.Model):
    tax_class = models.ForeignKey(TaxClassNfe, verbose_name="Classe de Nota Fiscal", on_delete=models.CASCADE, related_name="icms_scenarios")
    position = models.PositiveIntegerField(verbose_name="Posição", default=0)
    tipo_tributacao = models.CharField(verbose_name="Tipo tributação", max_length=30, blank=True, default="")
    cenario = models.CharField(verbose_name="Cenário", max_length=30, blank=True, default="")
    tipo_pessoa = models.CharField(verbose_name="Tipo pessoa", max_length=20, blank=True, default="")
    nao_contribuinte = models.BooleanField(verbose_name="Não contribuinte", null=True, blank=True)
    codigo_cfop = models.CharField(verbose_name="Código CFOP", max_length=20, blank=True, default="")
    situacao_tributaria = models.CharField(verbose_name="Situação tributária", max_length=10, blank=True, default="")
    aliquota_credito = models.DecimalField(verbose_name="Alíquota crédito", max_digits=7, decimal_places=2, null=True, blank=True)
    aliquota_importacao = models.DecimalField(verbose_name="Alíquota importação", max_digits=7, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["tax_class", "position"]),
        ]


class TaxClassNfeIpiScenario(models.Model):
    tax_class = models.ForeignKey(TaxClassNfe, verbose_name="Classe de Nota Fiscal", on_delete=models.CASCADE, related_name="ipi_scenarios")
    position = models.PositiveIntegerField(verbose_name="Posição", default=0)
    cenario = models.CharField(verbose_name="Cenário", max_length=30, blank=True, default="")
    tipo_pessoa = models.CharField(verbose_name="Tipo pessoa", max_length=20, blank=True, default="")
    situacao_tributaria = models.CharField(verbose_name="Situação tributária", max_length=10, blank=True, default="")
    codigo_enquadramento = models.CharField(verbose_name="Código enquadramento", max_length=10, blank=True, default="")
    aliquota = models.DecimalField(verbose_name="Alíquota", max_digits=7, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["tax_class", "position"]),
        ]


class TaxClassNfePisScenario(models.Model):
    tax_class = models.ForeignKey(TaxClassNfe, verbose_name="Classe de Nota Fiscal", on_delete=models.CASCADE, related_name="pis_scenarios")
    position = models.PositiveIntegerField(verbose_name="Posição", default=0)
    cenario = models.CharField(verbose_name="Cenário", max_length=30, blank=True, default="")
    tipo_pessoa = models.CharField(verbose_name="Tipo pessoa", max_length=20, blank=True, default="")
    situacao_tributaria = models.CharField(verbose_name="Situação tributária", max_length=10, blank=True, default="")
    aliquota = models.DecimalField(verbose_name="Alíquota", max_digits=7, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["tax_class", "position"]),
        ]


class TaxClassNfeCofinsScenario(models.Model):
    tax_class = models.ForeignKey(TaxClassNfe, verbose_name="Classe de Nota Fiscal", on_delete=models.CASCADE, related_name="cofins_scenarios")
    position = models.PositiveIntegerField(verbose_name="Posição", default=0)
    cenario = models.CharField(verbose_name="Cenário", max_length=30, blank=True, default="")
    tipo_pessoa = models.CharField(verbose_name="Tipo pessoa", max_length=20, blank=True, default="")
    situacao_tributaria = models.CharField(verbose_name="Situação tributária", max_length=10, blank=True, default="")
    aliquota = models.DecimalField(verbose_name="Alíquota", max_digits=7, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["tax_class", "position"]),
        ]


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
        return f"Nota Fiscal de Serviço {self.reference} ({workshop_id})"


class TaxClassSyncState(TimeStampedModel):
    workshop = models.OneToOneField("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="tax_class_sync_state")
    synced_once = models.BooleanField(verbose_name="Sincronização inicial concluída", default=False)

    def __str__(self) -> str:
        state = "ok" if self.synced_once else "pending"
        workshop_id = getattr(self, "workshop_id", "-")
        return f"TaxClassSyncState[{state}] ({workshop_id})"


class TaxClassPresetKind(models.TextChoices):
    NFE = "nfe", "Nota Fiscal"
    NFSE = "nfse", "Nota Fiscal de Serviço"


class TaxClassPreset(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="tax_class_presets")
    kind = models.CharField(verbose_name="Tipo", max_length=10, choices=TaxClassPresetKind.choices)
    name = models.CharField(verbose_name="Nome do preset", max_length=120)
    description = models.CharField(verbose_name="Descrição do preset", max_length=255, blank=True, default="")
    is_active = models.BooleanField(verbose_name="Ativo", default=True)
    payload = models.JSONField(verbose_name="Payload", blank=True, default=dict)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "kind", "name"], name="unique_tax_class_preset_per_workshop_kind_name"),
        ]
        indexes = [
            models.Index(fields=["workshop", "kind", "is_active"]),
        ]
        ordering = ["kind", "name", "id"]

    def __str__(self) -> str:
        workshop_id = getattr(self, "workshop_id", "-")
        return f"Preset {self.get_kind_display()} {self.name} ({workshop_id})"


class WebmaniaCompanyTaxType(models.TextChoices):
    SIMPLES_NACIONAL = "simples_nacional", "Simples Nacional"
    LUCRO_NORMAL = "lucro_normal", "Lucro Normal"


class WebmaniaCompany(TimeStampedModel):
    workshop = models.OneToOneField("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="webmania_company", null=True, blank=True)

    webmania_company_id = models.CharField(verbose_name="ID da empresa na Webmania", max_length=32, blank=True, default="")
    consumer_key = models.CharField(verbose_name="Consumer Key", max_length=255, blank=True, default="")
    consumer_secret = models.CharField(verbose_name="Consumer Secret", max_length=255, blank=True, default="")
    access_token = models.CharField(verbose_name="Access Token", max_length=255, blank=True, default="")
    access_token_secret = models.CharField(verbose_name="Access Token Secret", max_length=255, blank=True, default="")
    bearer_access_token = models.CharField(verbose_name="Bearer Access Token", max_length=255, blank=True, default="")

    tipo_tributacao = models.CharField(verbose_name="Tipo tributação", max_length=32, choices=WebmaniaCompanyTaxType.choices, blank=True, default="")
    regime_tributario = models.CharField(verbose_name="Regime tributário", max_length=32, blank=True, default="")
    cnpj = models.CharField(verbose_name="CNPJ", max_length=18, blank=True, default="")
    razao_social = models.CharField(verbose_name="Razão social", max_length=120, blank=True, default="")
    cpf = models.CharField(verbose_name="CPF", max_length=14, blank=True, default="")
    nome_completo = models.CharField(verbose_name="Nome completo", max_length=120, blank=True, default="")
    nome_fantasia = models.CharField(verbose_name="Nome fantasia", max_length=120, blank=True, default="")
    ie = models.CharField(verbose_name="Inscrição estadual", max_length=20, blank=True, default="")
    im = models.CharField(verbose_name="Inscrição municipal", max_length=20, blank=True, default="")
    unidade_empresa = models.CharField(verbose_name="Unidade da empresa", max_length=16, blank=True, default="")
    email = models.CharField(verbose_name="E-mail", max_length=120, blank=True, default="")
    telefone = models.CharField(verbose_name="Telefone", max_length=20, blank=True, default="")
    conta_bancaria_banco = models.CharField(verbose_name="Banco", max_length=8, blank=True, default="")
    conta_bancaria_agencia = models.CharField(verbose_name="Agência", max_length=10, blank=True, default="")
    conta_bancaria_numero = models.CharField(verbose_name="Conta", max_length=30, blank=True, default="")
    conta_bancaria_digito = models.CharField(verbose_name="Dígito da conta", max_length=4, blank=True, default="")
    contabilidade = models.CharField(verbose_name="Contabilidade", max_length=255, blank=True, default="")
    url_notificacao = models.CharField(verbose_name="URL notificação", max_length=255, blank=True, default="")
    logomarca = models.CharField(verbose_name="Logomarca", max_length=255, blank=True, default="")

    cep = models.CharField(verbose_name="CEP", max_length=10, blank=True, default="")
    endereco = models.CharField(verbose_name="Endereço", max_length=120, blank=True, default="")
    numero = models.CharField(verbose_name="Número", max_length=20, blank=True, default="")
    complemento = models.CharField(verbose_name="Complemento", max_length=120, blank=True, default="")
    bairro = models.CharField(verbose_name="Bairro", max_length=120, blank=True, default="")
    cidade = models.CharField(verbose_name="Cidade", max_length=120, blank=True, default="")
    uf = models.CharField(verbose_name="UF", max_length=2, blank=True, default="")

    nfe_serie = models.PositiveIntegerField(verbose_name="Série da Nota Fiscal", null=True, blank=True)
    nfe_numero = models.PositiveIntegerField(verbose_name="Próximo número da Nota Fiscal", null=True, blank=True)
    nfe_numero_dev = models.PositiveIntegerField(verbose_name="Próximo número da Nota Fiscal homologação", null=True, blank=True)
    cnae_issqn = models.CharField(verbose_name="CNAE ISSQN", max_length=10, blank=True, default="")

    nfce_enabled = models.BooleanField(verbose_name="NFC-e habilitada", default=False)
    nfce_serie = models.PositiveIntegerField(verbose_name="Série NFC-e", null=True, blank=True)
    nfce_numero = models.PositiveIntegerField(verbose_name="Próximo número NFC-e", null=True, blank=True)
    nfce_id_csc = models.CharField(verbose_name="ID CSC NFC-e", max_length=255, blank=True, default="")
    nfce_codigo_csc = models.CharField(verbose_name="Código CSC NFC-e", max_length=255, blank=True, default="")
    nfce_numero_dev = models.PositiveIntegerField(verbose_name="Próximo número NFC-e homologação", null=True, blank=True)
    nfce_id_csc_dev = models.CharField(verbose_name="ID CSC NFC-e homologação", max_length=255, blank=True, default="")
    nfce_codigo_csc_dev = models.CharField(verbose_name="Código CSC NFC-e homologação", max_length=255, blank=True, default="")
    credit_debit_basis_enabled = models.BooleanField(verbose_name="Preparacao de base credito/debito habilitada", default=False)
    credit_debit_basis_enabled_by = models.ForeignKey("accounts.User", verbose_name="Base credito/debito habilitada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="enabled_credit_debit_basis_companies")
    credit_debit_basis_enabled_at = models.DateTimeField(verbose_name="Base credito/debito habilitada em", null=True, blank=True)
    nfe_debit_emission_enabled = models.BooleanField(verbose_name="Emissao NF-e de debito habilitada", default=False)
    nfe_debit_emission_enabled_by = models.ForeignKey("accounts.User", verbose_name="Emissao NF-e de debito habilitada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="enabled_nfe_debit_emission_companies")
    nfe_debit_emission_enabled_at = models.DateTimeField(verbose_name="Emissao NF-e de debito habilitada em", null=True, blank=True)

    informacoes_fisco = models.TextField(verbose_name="Informações ao fisco", blank=True, default="")
    nfse_rps_serie = models.CharField(verbose_name="Série RPS da Nota Fiscal de Serviço", max_length=10, blank=True, default="")
    nfse_rps_numero = models.PositiveIntegerField(verbose_name="Próximo RPS NFS-e", null=True, blank=True)
    cnae = models.CharField(verbose_name="CNAE NFS-e", max_length=255, blank=True, default="")
    nfse_login = models.CharField(verbose_name="Login NFS-e", max_length=120, blank=True, default="")
    nfse_password = models.CharField(verbose_name="Senha NFS-e", max_length=255, blank=True, default="")
    nfse_token = models.CharField(verbose_name="Token NFS-e", max_length=255, blank=True, default="")
    regime_apuracao_sn = models.CharField(verbose_name="Regime apuração SN", max_length=4, blank=True, default="")
    regime_especial_nacional = models.CharField(verbose_name="Regime especial nacional", max_length=4, blank=True, default="")
    regime_especial_municipal = models.CharField(verbose_name="Regime especial municipal", max_length=4, blank=True, default="")
    nfse_lote_rps_numero = models.PositiveIntegerField(verbose_name="Próximo lote RPS", null=True, blank=True)
    nfse_rps_numero_dev = models.PositiveIntegerField(verbose_name="Próximo RPS homologação", null=True, blank=True)

    certificado = models.TextField(verbose_name="Certificado A1 em Base64", blank=True, default="")
    certificado_senha = models.CharField(verbose_name="Senha certificado A1", max_length=255, blank=True, default="")

    partilha_icms_contribuinte = models.BooleanField(verbose_name="Partilha ICMS contribuinte", null=True, blank=True)
    partilha_icms_isento = models.BooleanField(verbose_name="Partilha ICMS isento", null=True, blank=True)
    orientacao_danfe = models.CharField(verbose_name="Orientação DANFE", max_length=2, blank=True, default="")
    microcervejaria = models.BooleanField(verbose_name="Microcervejaria", null=True, blank=True)
    icms_ref_sp = models.BooleanField(verbose_name="ICMS refeição SP", null=True, blank=True)
    refeicoes_sp = models.BooleanField(verbose_name="Regime refeições SP", null=True, blank=True)
    icms_ref_df = models.BooleanField(verbose_name="ICMS refeição DF", null=True, blank=True)
    exclusao_icms_pis_cofins = models.BooleanField(verbose_name="Exclusão ICMS PIS/COFINS", null=True, blank=True)
    exclusao_difal_pis_cofins = models.BooleanField(verbose_name="Exclusão DIFAL PIS/COFINS", null=True, blank=True)
    deduzir_desconto_ipi = models.BooleanField(verbose_name="Deduzir desconto IPI", null=True, blank=True)
    email_automatico_nfse = models.BooleanField(verbose_name="E-mail automático NFS-e", null=True, blank=True)
    nfse_legacy_compatibility_enabled = models.BooleanField(verbose_name="Compatibilidade legada NFS-e habilitada", default=True)
    nfse_substitution_preview_enabled = models.BooleanField(verbose_name="Preview de substituicao NFS-e habilitada", default=False)
    nfse_manual_emission_preview_enabled = models.BooleanField(verbose_name="Preview de emissao manual NFS-e habilitada", default=False)
    nfse_manual_emission_enabled = models.BooleanField(verbose_name="Emissao manual NFS-e habilitada", default=False)
    nfse_received_import_enabled = models.BooleanField(verbose_name="Importacao de NFS-e recebida habilitada", default=False)
    nfse_received_consultation_enabled = models.BooleanField(verbose_name="Consulta de NFS-e recebida habilitada", default=False)
    nfse_external_xml_inbox_enabled = models.BooleanField(verbose_name="Inbox externa de XML NFS-e habilitada", default=False)
    desativar_epec = models.CharField(verbose_name="Desativar EPEC", max_length=4, blank=True, default="")
    ocultar_total_etiqueta = models.CharField(verbose_name="Ocultar total etiqueta", max_length=4, blank=True, default="")

    last_sync_at = models.DateTimeField(verbose_name="Última sincronização", null=True, blank=True)
    last_sync_error = models.TextField(verbose_name="Último erro de sincronização", blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["webmania_company_id"]),
            models.Index(fields=["cnpj"]),
            models.Index(fields=["cpf"]),
        ]

    def __str__(self) -> str:
        workshop_id = getattr(self, "workshop_id", "-")
        label = self.razao_social or self.nome_completo or self.webmania_company_id or "sem-id"
        return f"WebmaniaCompany[{label}] ({workshop_id})"


class NfseRequest(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE)
    current_step = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=NfseRequestStatus.choices, default=NfseRequestStatus.WAITING_WO)
    pricing_slider = models.SmallIntegerField(
        verbose_name="Slider de precificacao",
        null=True,
        blank=True,
        validators=[MinValueValidator(-100), MaxValueValidator(100)],
        help_text="Copia o slider do orcamento na criacao e permanece independente para a emissao.",
    )
    service_description = models.TextField(verbose_name="Discriminação do Serviço", blank=True, default="")
    additional_information = models.TextField(verbose_name="Informações complementares", blank=True, default="")
    tax_class = models.CharField(verbose_name="Classe de Imposto", max_length=30, default="REF000000")
    reserved_rps_number = models.PositiveIntegerField(verbose_name="RPS reservado", null=True, blank=True)
    reserved_rps_series = models.CharField(verbose_name="Série RPS reservada", max_length=20, blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        permissions = [
            ("query_nfse", "Pode consultar NFS-e por UUID"),
            ("query_nfse_batch", "Pode consultar lote RPS por UUID"),
            ("cancel_nfse", "Pode cancelar NFS-e"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is None and self.pricing_slider is None:
            default_slider = _default_pricing_slider_from_workorder(workorder_id=self.workorder_id, workorder=getattr(self, "workorder", None))
            if default_slider is not None:
                self.pricing_slider = default_slider

        super().save(*args, **kwargs)

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

        normalized_status = normalize_nfse_request_status(request_status)
        status_mapping = {
            "processing": NfseRequestStatus.PROCESSING,
            "approved": NfseRequestStatus.APPROVED,
            "reproved": NfseRequestStatus.REPROVED,
            "scheduled": NfseRequestStatus.SCHEDULED,
            "canceled": NfseRequestStatus.CANCELED,
            "contingency": NfseRequestStatus.CONTINGENCY,
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

    @property
    def rps_number_display(self) -> str:
        if self.reserved_rps_number is not None:
            return str(self.reserved_rps_number)

        first_item = self.items.order_by("id").first()
        if first_item is None:
            return "-"

        return str(first_item.rps_number or first_item.number or "-")


class NfeRequest(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE)
    current_step = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=NfeRequestStatus.choices, default=NfeRequestStatus.WAITING_WO)
    pricing_slider = models.SmallIntegerField(
        verbose_name="Slider de precificacao",
        null=True,
        blank=True,
        validators=[MinValueValidator(-100), MaxValueValidator(100)],
        help_text="Copia o slider do orcamento na criacao e permanece independente para a emissao.",
    )
    additional_information = models.TextField(verbose_name="Informações complementares", blank=True, default="")
    tax_class = models.CharField(verbose_name="Classe de Imposto", max_length=30, default="REF000000")
    reserved_number = models.PositiveIntegerField(verbose_name="Número reservado", null=True, blank=True)
    reserved_series = models.PositiveIntegerField(verbose_name="Série reservada", null=True, blank=True)
    invalidation_reason = models.TextField(verbose_name="Motivo da inutilização", blank=True, default="")
    invalidation_xml_url = models.URLField(verbose_name="XML da inutilização", blank=True, default="")
    invalidation_log_payload = models.JSONField(verbose_name="Log da inutilização", blank=True, default=dict)
    invalidated_at = models.DateTimeField(verbose_name="Data da inutilização", null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.pk is None and self.pricing_slider is None:
            default_slider = _default_pricing_slider_from_workorder(workorder_id=self.workorder_id, workorder=getattr(self, "workorder", None))
            if default_slider is not None:
                self.pricing_slider = default_slider

        super().save(*args, **kwargs)

    def set_status(self, status: NfeRequestStatus):
        self.status = status
        self.save(update_fields=["status"])

    @property
    def customer_name(self) -> str:
        customer = getattr(getattr(self.workorder, "budget", None), "customer", None)
        if not customer:
            return "-"
        return customer.name

    @property
    def nfe_request_status_badge(self) -> dict[str, str]:
        status_color = {
            NfeRequestStatus.WAITING_WO: "badge-soft badge-ghost",
            NfeRequestStatus.CHECKING_CLIENT: "badge-soft badge-info",
            NfeRequestStatus.CHECKING_PRODUCTS: "badge-soft badge-info",
            NfeRequestStatus.PROCESSING: "badge-soft badge-warning",
            NfeRequestStatus.APPROVED: "badge-success",
            NfeRequestStatus.REPROVED: "badge-error",
            NfeRequestStatus.DENIED: "badge-soft badge-error",
            NfeRequestStatus.CANCELED: "badge-soft badge-error",
            NfeRequestStatus.CONTINGENCY: "badge-soft badge-warning",
            NfeRequestStatus.INVALIDATED: "badge-soft badge-error",
        }

        return {
            "text": str(NfeRequestStatus(self.status).label),
            "class": status_color.get(self.status, "badge-ghost"),
        }

    def update_status_based_on_request(self, request_status: str | None) -> bool:
        if not request_status:
            return False

        normalized_status = normalize_nfe_request_status(request_status)
        status_mapping = {
            "processing": NfeRequestStatus.PROCESSING,
            "approved": NfeRequestStatus.APPROVED,
            "reproved": NfeRequestStatus.REPROVED,
            "canceled": NfeRequestStatus.CANCELED,
            "denied": NfeRequestStatus.DENIED,
            "contingency": NfeRequestStatus.CONTINGENCY,
        }
        mapped_status = status_mapping.get(normalized_status)
        if not mapped_status:
            logger.warning("Status desconhecido recebido no webhook de NF-e", extra={"request_status": request_status})
            return False

        self.set_status(mapped_status)
        return True

    def __str__(self):
        workorder_pk = getattr(self, "workorder_id", None) or "-"
        return f"NF-e Request #{self.pk} - OS #{workorder_pk}"

    @property
    def number_display(self) -> str:
        if self.reserved_number is not None:
            return str(self.reserved_number)

        first_item = self.items.order_by("id").first()
        if first_item is None:
            return "-"

        return str(first_item.number or "-")


class NfseMunicipalCapability(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_municipal_capabilities")
    company = models.ForeignKey(WebmaniaCompany, verbose_name="Empresa Webmania", on_delete=models.PROTECT, related_name="nfse_municipal_capabilities")
    city_code = models.CharField(verbose_name="Codigo IBGE do municipio", max_length=7)
    city_name = models.CharField(verbose_name="Municipio", max_length=120)
    state = models.CharField(verbose_name="UF", max_length=2)
    provider = models.CharField(verbose_name="Provedor/modelo", max_length=80, blank=True, default="")
    provider_version = models.CharField(verbose_name="Versao do provedor", max_length=40, blank=True, default="")
    is_active = models.BooleanField(verbose_name="Capacidade ativa", default=True)
    national_standard_enabled = models.BooleanField(verbose_name="Padrao Nacional", default=False)
    legacy_municipal_enabled = models.BooleanField(verbose_name="Padrao municipal legado", default=True)
    emission_enabled = models.BooleanField(verbose_name="Emissao habilitada", default=False)
    manual_emission_enabled = models.BooleanField(verbose_name="Emissao manual habilitada", default=False)
    query_enabled = models.BooleanField(verbose_name="Consulta habilitada", default=True)
    cancellation_enabled = models.BooleanField(verbose_name="Cancelamento habilitado", default=False)
    substitution_enabled = models.BooleanField(verbose_name="Substituicao habilitada", default=False)
    manifestation_enabled = models.BooleanField(verbose_name="Manifestacao habilitada", default=False)
    batch_required = models.BooleanField(verbose_name="Lote RPS obrigatorio", default=False)
    rps_required = models.BooleanField(verbose_name="RPS obrigatorio", default=True)
    synchronous_emission = models.BooleanField(verbose_name="Emissao sincrona", default=False)
    xml_download_enabled = models.BooleanField(verbose_name="Download XML disponivel", default=True)
    pdf_download_enabled = models.BooleanField(verbose_name="Download PDF NFS-e disponivel", default=True)
    rps_pdf_enabled = models.BooleanField(verbose_name="Download PDF RPS disponivel", default=True)
    requires_municipal_registration = models.BooleanField(verbose_name="Exige inscricao municipal", default=False)
    requires_service_code = models.BooleanField(verbose_name="Exige codigo de servico", default=False)
    requires_cnae = models.BooleanField(verbose_name="Exige CNAE", default=False)
    requires_iss_rate = models.BooleanField(verbose_name="Exige aliquota ISS", default=False)
    remote_payload = models.JSONField(verbose_name="Payload remoto sanitizado", blank=True, default=dict)
    remote_status = models.BooleanField(verbose_name="Status remoto do municipio", null=True, blank=True)
    last_synced_at = models.DateTimeField(verbose_name="Ultima sincronizacao", null=True, blank=True)
    last_status_error = models.TextField(verbose_name="Ultimo erro de consulta", blank=True, default="")
    notes = models.TextField(verbose_name="Observacoes", blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "company", "city_code"], name="unique_nfse_capability_scope"),
        ]
        indexes = [
            models.Index(fields=["workshop", "city_code", "is_active"], name="nfse_cap_workshop_city_idx"),
            models.Index(fields=["company", "state", "city_name"], name="nfse_cap_company_city_idx"),
        ]
        permissions = [
            ("manage_nfse_capabilities", "Pode gerenciar capacidades municipais NFS-e"),
            ("query_nfse_status", "Pode consultar status municipal NFS-e"),
        ]

    def clean(self) -> None:
        super().clean()
        self.city_code = str(self.city_code or "").strip()
        self.city_name = str(self.city_name or "").strip()
        self.state = str(self.state or "").strip().upper()
        if not self.city_code.isdigit() or len(self.city_code) != 7:
            raise ValidationError({"city_code": "Informe o codigo IBGE do municipio com 7 digitos."})
        if len(self.state) != 2:
            raise ValidationError({"state": "Informe a UF com 2 caracteres."})
        if self.company_id and self.workshop_id and self.company.workshop_id != self.workshop_id:
            raise ValidationError({"company": "A empresa Webmania deve pertencer a oficina informada."})

    def __str__(self) -> str:
        return f"NFS-e {self.city_name}/{self.state} [{self.workshop_id}]"


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
    last_webhook_at = models.DateTimeField(null=True, blank=True)
    remote_updated_at = models.DateTimeField(verbose_name="Atualizacao remota canonica", null=True, blank=True, db_index=True)
    last_reconciled_at = models.DateTimeField(verbose_name="Ultima consulta", null=True, blank=True)
    last_update_source = models.CharField(verbose_name="Origem da ultima atualizacao", max_length=20, blank=True, default="")
    last_sync_error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workorder", "uuid"], name="unique_nfse_batch_per_workorder"),
        ]

        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]


class NfseItem(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE, null=True, blank=True)
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
    last_webhook_at = models.DateTimeField(null=True, blank=True)
    remote_updated_at = models.DateTimeField(verbose_name="Atualizacao remota canonica", null=True, blank=True, db_index=True)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    last_update_source = models.CharField(verbose_name="Origem da ultima atualizacao", max_length=20, blank=True, default="")
    last_sync_error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workorder", "uuid"], name="unique_nfse_item_per_workorder"),
        ]

        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]


class NfseCancellation(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_cancellations")
    request = models.ForeignKey(NfseRequest, verbose_name="Requisicao NFS-e", on_delete=models.CASCADE, null=True, blank=True, related_name="cancellations")
    item = models.ForeignKey(NfseItem, verbose_name="NFS-e", on_delete=models.PROTECT, related_name="cancellations")
    status = models.CharField(max_length=20, choices=FiscalEmissionAttemptStatus.choices, default=FiscalEmissionAttemptStatus.STARTED, db_index=True)
    reason_code = models.PositiveSmallIntegerField(verbose_name="Motivo")
    reason_label = models.CharField(max_length=80)
    request_payload = models.JSONField(blank=True, default=dict)
    response_payload = models.JSONField(blank=True, default=dict)
    xml_url = models.URLField(blank=True, default="")
    requested_by = models.ForeignKey("accounts.User", verbose_name="Solicitante", on_delete=models.SET_NULL, null=True, blank=True, related_name="nfse_cancellations")
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["item"],
                condition=models.Q(status__in=[FiscalEmissionAttemptStatus.STARTED, FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED, FiscalEmissionAttemptStatus.UNCERTAIN]),
                name="unique_active_nfse_cancellation",
            ),
        ]
        indexes = [
            models.Index(fields=["workshop", "status"], name="nfse_cancel_scope_status_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and self.request_payload:
            previous_payload = type(self).objects.filter(pk=self.pk).values_list("request_payload", flat=True).first()
            if previous_payload and previous_payload != self.request_payload:
                raise ValidationError("O payload do cancelamento NFS-e nao pode ser alterado apos ser persistido.")
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.item_id and self.workshop_id and self.item.workshop_id != self.workshop_id:
            raise ValidationError("O cancelamento e a NFS-e devem pertencer a mesma oficina.")
        if self.item_id and self.request_id and self.item.request_id != self.request_id:
            raise ValidationError("O cancelamento e a NFS-e devem pertencer a mesma requisicao.")

    def __str__(self) -> str:
        return f"NfseCancellation[{self.item_id}:{self.status}]"


class NfseSubstitutionPreview(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_substitution_previews")
    original_nfse = models.ForeignKey(NfseItem, verbose_name="NFS-e original", on_delete=models.PROTECT, related_name="substitution_previews")
    original_uuid = models.UUIDField(verbose_name="UUID original", db_index=True)
    original_verification_code = models.CharField(verbose_name="Codigo de verificacao original", max_length=60)
    original_xml_snapshot = models.JSONField(verbose_name="Snapshot do XML original", default=dict)
    environment = models.CharField(verbose_name="Ambiente", max_length=1, choices=(("1", "Producao"), ("2", "Homologacao")))
    reason_code = models.PositiveSmallIntegerField(verbose_name="Motivo", choices=((1, "Erro na emissao"), (2, "Servico nao prestado"), (4, "Duplicidade da nota")))
    rps_payload = models.JSONField(verbose_name="Novo RPS congelado", default=dict)
    request_payload = models.JSONField(verbose_name="Pre-payload de substituicao", default=dict)
    validation_status = models.CharField(verbose_name="Status", max_length=16, choices=FiscalProductPreviewStatus.choices, default=FiscalProductPreviewStatus.DRAFT, db_index=True)
    validation_errors = models.JSONField(verbose_name="Erros de validacao", default=list, blank=True)
    forbidden_fields_detected = models.JSONField(verbose_name="Campos proibidos detectados", default=list, blank=True)
    is_approved = models.BooleanField(verbose_name="Aprovada", default=False, db_index=True)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_nfse_substitution_previews")
    approved_by = models.ForeignKey("accounts.User", verbose_name="Aprovada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_nfse_substitution_previews")
    approved_at = models.DateTimeField(verbose_name="Aprovada em", null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["original_nfse"], condition=models.Q(is_approved=True), name="unique_approved_nfse_subst_preview"),
        ]
        indexes = [
            models.Index(fields=["workshop", "validation_status"], name="nfse_subst_prev_scope_idx"),
            models.Index(fields=["original_nfse", "is_approved"], name="nfse_subst_prev_orig_idx"),
        ]
        permissions = [
            ("prepare_nfse_substitution", "Pode preparar substituicao NFS-e"),
            ("approve_nfse_substitution", "Pode aprovar substituicao NFS-e"),
            ("view_nfse_substitution_preview", "Pode visualizar preview de substituicao NFS-e"),
            ("view_nfse_substitution_preview_payload", "Pode visualizar payload da preview de substituicao NFS-e"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.original_nfse_id and self.original_nfse.workshop_id != self.workshop_id:
            raise ValidationError({"original_nfse": "A NFS-e original pertence a outra oficina."})
        if self.original_nfse_id and str(self.original_nfse.uuid) != str(self.original_uuid):
            raise ValidationError({"original_uuid": "O UUID congelado diverge da NFS-e original."})
        if self.original_nfse_id and self.original_nfse.verification_code != self.original_verification_code:
            raise ValidationError({"original_verification_code": "O codigo de verificacao congelado diverge da NFS-e original."})
        if self.original_nfse_id and self.original_nfse.status != NfseItemStatus.aprovado:
            raise ValidationError({"original_nfse": "A preview exige NFS-e original autorizada."})
        if not self.original_verification_code.strip():
            raise ValidationError({"original_verification_code": "Codigo de verificacao obrigatorio."})
        if not isinstance(self.original_xml_snapshot, dict) or not self.original_xml_snapshot.get("url"):
            raise ValidationError({"original_xml_snapshot": "O XML original deve possuir snapshot com URL."})
        required_rps = ("numero", "serie", "servico", "tomador")
        missing_rps = [field for field in required_rps if self.rps_payload.get(field) in (None, "", {})]
        if missing_rps:
            raise ValidationError({"rps_payload": f"Novo RPS incompleto: {', '.join(missing_rps)}."})
        if self.forbidden_fields_detected:
            raise ValidationError({"forbidden_fields_detected": "A preview contem campos fora do contrato preparatorio."})
        expected_request = {
            "ambiente": int(self.environment),
            "codigo_verificacao": self.original_verification_code,
            "motivo": self.reason_code,
            "rps": self.rps_payload,
        }
        if self.request_payload != expected_request:
            raise ValidationError({"request_payload": "O pre-payload nao corresponde aos dados congelados."})
        if self.is_approved != (self.validation_status == FiscalProductPreviewStatus.APPROVED):
            raise ValidationError("Status e marcador de aprovacao devem permanecer consistentes.")
        if self.is_approved and (self.approved_by_id is None or self.approved_at is None):
            raise ValidationError("A aprovacao exige usuario e timestamp.")

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = (
                "workshop_id",
                "original_nfse_id",
                "original_uuid",
                "original_verification_code",
                "original_xml_snapshot",
                "environment",
                "reason_code",
                "rps_payload",
                "request_payload",
                "forbidden_fields_detected",
            )
            persisted = type(self).objects.filter(pk=self.pk).values("is_approved", "validation_status", *immutable_fields).first()
            if persisted and persisted["is_approved"]:
                changed_payload = any(persisted[field] != getattr(self, field) for field in immutable_fields)
                changed_approval = not self.is_approved or self.validation_status != FiscalProductPreviewStatus.APPROVED
                if changed_payload or changed_approval:
                    raise ValidationError("Os dados e o estado de uma preview de substituicao aprovada sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseSubstitutionPreview[{self.original_nfse_id}:{self.validation_status}]"


class NfseManualEmissionPreview(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_manual_emission_previews")
    company = models.ForeignKey(WebmaniaCompany, verbose_name="Empresa Webmania", on_delete=models.PROTECT, related_name="nfse_manual_emission_previews")
    municipal_capability = models.ForeignKey(NfseMunicipalCapability, verbose_name="Capacidade municipal", on_delete=models.PROTECT, related_name="manual_emission_previews")
    environment = models.CharField(verbose_name="Ambiente", max_length=1, choices=(("1", "Producao"), ("2", "Homologacao")))
    rps_number = models.PositiveIntegerField(verbose_name="Numero RPS")
    rps_series = models.CharField(verbose_name="Serie RPS", max_length=20)
    rps_payload = models.JSONField(verbose_name="RPS congelado", default=dict)
    request_payload = models.JSONField(verbose_name="Payload planejado", default=dict)
    taker_snapshot = models.JSONField(verbose_name="Snapshot do tomador", default=dict)
    service_snapshot = models.JSONField(verbose_name="Snapshot do servico", default=dict)
    values_snapshot = models.JSONField(verbose_name="Snapshot de valores", default=dict)
    taxation_snapshot = models.JSONField(verbose_name="Snapshot de tributacao", default=dict)
    retention_snapshot = models.JSONField(verbose_name="Snapshot de retencoes", default=dict, blank=True)
    ibs_cbs_snapshot = models.JSONField(verbose_name="Snapshot IBS/CBS", default=dict, blank=True)
    validation_status = models.CharField(verbose_name="Status", max_length=16, choices=FiscalProductPreviewStatus.choices, default=FiscalProductPreviewStatus.DRAFT, db_index=True)
    validation_errors = models.JSONField(verbose_name="Erros de validacao", default=list, blank=True)
    forbidden_fields_detected = models.JSONField(verbose_name="Campos proibidos detectados", default=list, blank=True)
    is_approved = models.BooleanField(verbose_name="Aprovada", default=False, db_index=True)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_nfse_manual_emission_previews")
    approved_by = models.ForeignKey("accounts.User", verbose_name="Aprovada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_nfse_manual_emission_previews")
    approved_at = models.DateTimeField(verbose_name="Aprovada em", null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["company", "environment", "rps_number", "rps_series"],
                condition=models.Q(is_approved=True),
                name="unique_approved_nfse_manual_rps",
            ),
        ]
        indexes = [
            models.Index(fields=["workshop", "validation_status"], name="nfse_manual_prev_scope_idx"),
            models.Index(fields=["company", "environment", "rps_number", "rps_series"], name="nfse_manual_prev_rps_idx"),
        ]
        permissions = [
            ("prepare_nfse_manual_emission_preview", "Pode preparar preview de emissao manual NFS-e"),
            ("approve_nfse_manual_emission_preview", "Pode aprovar preview de emissao manual NFS-e"),
            ("view_nfse_manual_emission_preview", "Pode visualizar preview de emissao manual NFS-e"),
            ("view_nfse_manual_emission_preview_payload", "Pode visualizar payload da preview de emissao manual NFS-e"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.company_id and self.workshop_id and self.company.workshop_id != self.workshop_id:
            raise ValidationError({"company": "A empresa Webmania deve pertencer a oficina."})
        if self.municipal_capability_id and self.workshop_id and self.municipal_capability.workshop_id != self.workshop_id:
            raise ValidationError({"municipal_capability": "A capacidade municipal deve pertencer a oficina."})
        if self.municipal_capability_id and self.company_id and self.municipal_capability.company_id != self.company_id:
            raise ValidationError({"municipal_capability": "A capacidade municipal deve pertencer a empresa emissora."})
        if self.environment not in {"1", "2"}:
            raise ValidationError({"environment": "Ambiente invalido."})
        if self.rps_number <= 0:
            raise ValidationError({"rps_number": "Numero RPS deve ser positivo."})
        if not self.rps_series.strip():
            raise ValidationError({"rps_series": "Serie RPS obrigatoria."})
        if self.rps_payload.get("numero") != self.rps_number or self.rps_payload.get("serie") != self.rps_series:
            raise ValidationError({"rps_payload": "RPS congelado diverge do numero/serie."})
        required_rps = ("numero", "serie", "servico", "tomador")
        missing_rps = [field for field in required_rps if self.rps_payload.get(field) in (None, "", {})]
        if missing_rps:
            raise ValidationError({"rps_payload": f"RPS incompleto: {', '.join(missing_rps)}."})
        expected_request = {"ambiente": int(self.environment), "rps": [self.rps_payload]}
        if self.request_payload != expected_request:
            raise ValidationError({"request_payload": "O payload planejado nao corresponde ao RPS congelado."})
        if self.forbidden_fields_detected:
            raise ValidationError({"forbidden_fields_detected": "A preview contem campos fora do contrato preparatorio."})
        if self.is_approved != (self.validation_status == FiscalProductPreviewStatus.APPROVED):
            raise ValidationError("Status e marcador de aprovacao devem permanecer consistentes.")
        if self.is_approved and (self.approved_by_id is None or self.approved_at is None):
            raise ValidationError("A aprovacao exige usuario e timestamp.")

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = (
                "workshop_id",
                "company_id",
                "municipal_capability_id",
                "environment",
                "rps_number",
                "rps_series",
                "rps_payload",
                "request_payload",
                "taker_snapshot",
                "service_snapshot",
                "values_snapshot",
                "taxation_snapshot",
                "retention_snapshot",
                "ibs_cbs_snapshot",
                "forbidden_fields_detected",
            )
            persisted = type(self).objects.filter(pk=self.pk).values("is_approved", "validation_status", *immutable_fields).first()
            if persisted and persisted["is_approved"]:
                changed_payload = any(persisted[field] != getattr(self, field) for field in immutable_fields)
                changed_approval = not self.is_approved or self.validation_status != FiscalProductPreviewStatus.APPROVED
                if changed_payload or changed_approval:
                    raise ValidationError("Os dados e o estado de uma preview manual NFS-e aprovada sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseManualEmissionPreview[{self.rps_number}/{self.rps_series}:{self.validation_status}]"


class NfseManualEmission(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_manual_emissions")
    company = models.ForeignKey(WebmaniaCompany, verbose_name="Empresa Webmania", on_delete=models.PROTECT, related_name="nfse_manual_emissions")
    preview = models.OneToOneField(NfseManualEmissionPreview, verbose_name="Preview aprovada", on_delete=models.PROTECT, related_name="manual_emission")
    nfse_item = models.OneToOneField(NfseItem, verbose_name="NFS-e emitida", on_delete=models.PROTECT, null=True, blank=True, related_name="manual_emission")
    environment = models.CharField(verbose_name="Ambiente", max_length=1, choices=(("1", "Producao"), ("2", "Homologacao")))
    rps_number = models.PositiveIntegerField(verbose_name="Numero RPS")
    rps_series = models.CharField(verbose_name="Serie RPS", max_length=20)
    request_payload = models.JSONField(verbose_name="Payload enviado", default=dict)
    response_payload = models.JSONField(verbose_name="Resposta remota", default=dict, blank=True)
    remote_uuid = models.UUIDField(verbose_name="UUID remoto", null=True, blank=True, db_index=True)
    verification_code = models.CharField(verbose_name="Codigo de verificacao", max_length=60, blank=True, default="")
    xml_nfse = models.URLField(verbose_name="XML NFS-e", blank=True, default="")
    danfse_pdf = models.URLField(verbose_name="DANFSE/PDF", blank=True, default="")
    status = models.CharField(max_length=20, choices=FiscalEmissionAttemptStatus.choices, default=FiscalEmissionAttemptStatus.STARTED, db_index=True)
    is_uncertain = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="nfse_manual_emissions")
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["company", "environment", "rps_number", "rps_series"],
                condition=models.Q(status__in=[FiscalEmissionAttemptStatus.STARTED, FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED, FiscalEmissionAttemptStatus.UNCERTAIN]),
                name="unique_active_nfse_manual_rps",
            ),
        ]
        indexes = [
            models.Index(fields=["workshop", "status"], name="nfse_manual_emit_scope_idx"),
            models.Index(fields=["company", "environment", "rps_number", "rps_series"], name="nfse_manual_emit_rps_idx"),
        ]
        permissions = [
            ("issue_nfse_manual_emission", "Pode emitir NFS-e manual"),
            ("view_nfse_manual_emission", "Pode visualizar emissao manual NFS-e"),
            ("download_nfse_manual_emission", "Pode baixar documentos da emissao manual NFS-e"),
            ("view_nfse_manual_emission_payload", "Pode visualizar payload da emissao manual NFS-e"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.company_id and self.workshop_id and self.company.workshop_id != self.workshop_id:
            raise ValidationError({"company": "A empresa Webmania deve pertencer a oficina."})
        if self.preview_id:
            if self.preview.workshop_id != self.workshop_id:
                raise ValidationError({"preview": "A preview pertence a outra oficina."})
            if self.preview.company_id != self.company_id:
                raise ValidationError({"preview": "A preview pertence a outra empresa emissora."})
            if not self.preview.is_approved or self.preview.validation_status != FiscalProductPreviewStatus.APPROVED:
                raise ValidationError({"preview": "A emissao manual exige preview aprovada."})
            if self.request_payload != self.preview.request_payload:
                raise ValidationError({"request_payload": "A emissao deve usar exatamente o payload aprovado da preview."})
        if self.nfse_item_id and self.nfse_item.workshop_id != self.workshop_id:
            raise ValidationError({"nfse_item": "A NFS-e emitida pertence a outra oficina."})
        if self.environment not in {"1", "2"}:
            raise ValidationError({"environment": "Ambiente invalido."})
        if self.rps_number <= 0 or not self.rps_series.strip():
            raise ValidationError("Numero e serie do RPS sao obrigatorios.")
        if self.is_uncertain != (self.status == FiscalEmissionAttemptStatus.UNCERTAIN):
            raise ValidationError("Status uncertain e marcador de incerteza devem permanecer consistentes.")

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = ("workshop_id", "company_id", "preview_id", "environment", "rps_number", "rps_series", "request_payload")
            persisted = type(self).objects.filter(pk=self.pk).values(*immutable_fields).first()
            if persisted and any(persisted[field] != getattr(self, field) for field in immutable_fields):
                raise ValidationError("A intencao e o payload da emissao manual NFS-e sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseManualEmission[{self.preview_id}:{self.status}]"


class NfseSubstitution(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_substitutions")
    preview = models.OneToOneField(NfseSubstitutionPreview, verbose_name="Preview aprovada", on_delete=models.PROTECT, related_name="substitution")
    original_nfse = models.ForeignKey(NfseItem, verbose_name="NFS-e original", on_delete=models.PROTECT, related_name="outgoing_substitutions")
    replacement_nfse = models.OneToOneField(NfseItem, verbose_name="NFS-e substituta", on_delete=models.PROTECT, null=True, blank=True, related_name="incoming_substitution")
    uuid_original = models.UUIDField(verbose_name="UUID original", db_index=True)
    uuid_replacement = models.UUIDField(verbose_name="UUID substituta", null=True, blank=True, db_index=True)
    original_verification_code = models.CharField(verbose_name="Codigo de verificacao original", max_length=60)
    reason_code = models.PositiveSmallIntegerField(verbose_name="Motivo")
    request_payload = models.JSONField(verbose_name="Payload enviado", default=dict)
    response_payload = models.JSONField(verbose_name="Resposta remota", default=dict, blank=True)
    original_xml_snapshot = models.JSONField(verbose_name="Snapshot XML original", default=dict)
    replacement_xml_url = models.URLField(verbose_name="XML substituta", blank=True, default="")
    replacement_pdf_url = models.URLField(verbose_name="PDF substituta", blank=True, default="")
    status = models.CharField(max_length=20, choices=FiscalEmissionAttemptStatus.choices, default=FiscalEmissionAttemptStatus.STARTED, db_index=True)
    is_uncertain = models.BooleanField(default=False, db_index=True)
    requested_by = models.ForeignKey("accounts.User", verbose_name="Solicitante", on_delete=models.SET_NULL, null=True, blank=True, related_name="nfse_substitutions")
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["original_nfse"], condition=models.Q(status__in=[FiscalEmissionAttemptStatus.STARTED, FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED, FiscalEmissionAttemptStatus.UNCERTAIN]), name="unique_active_nfse_substitution"),
        ]
        indexes = [models.Index(fields=["workshop", "status"], name="nfse_subst_scope_status_idx")]
        permissions = [
            ("substitute_nfse", "Pode substituir NFS-e"),
            ("view_nfse_substitution_payload", "Pode visualizar payload da substituicao NFS-e"),
            ("download_nfse_substitution", "Pode baixar documentos da substituicao NFS-e"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.preview_id and (not self.preview.is_approved or self.preview.validation_status != FiscalProductPreviewStatus.APPROVED):
            raise ValidationError({"preview": "A substituicao exige preview aprovada."})
        if self.preview_id and self.preview.workshop_id != self.workshop_id:
            raise ValidationError({"preview": "A preview pertence a outra oficina."})
        if self.original_nfse_id and self.original_nfse.workshop_id != self.workshop_id:
            raise ValidationError({"original_nfse": "A NFS-e original pertence a outra oficina."})
        if self.preview_id and self.original_nfse_id and self.preview.original_nfse_id != self.original_nfse_id:
            raise ValidationError("A original deve corresponder a preview aprovada.")
        if self.replacement_nfse_id and self.replacement_nfse.workshop_id != self.workshop_id:
            raise ValidationError({"replacement_nfse": "A substituta pertence a outra oficina."})
        if self.is_uncertain != (self.status == FiscalEmissionAttemptStatus.UNCERTAIN):
            raise ValidationError("Status uncertain e marcador de incerteza devem permanecer consistentes.")

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = ("workshop_id", "preview_id", "original_nfse_id", "uuid_original", "original_verification_code", "reason_code", "request_payload", "original_xml_snapshot")
            persisted = type(self).objects.filter(pk=self.pk).values(*immutable_fields).first()
            if persisted and any(persisted[field] != getattr(self, field) for field in immutable_fields):
                raise ValidationError("A intencao e o payload da substituicao NFS-e sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseSubstitution[{self.original_nfse_id}:{self.status}]"


class NfseManifestation(TimeStampedModel):
    class ManifestationType(models.TextChoices):
        CONFIRMATION = "confirmation", "Confirmacao"
        REJECTION = "rejection", "Rejeicao"

    class ManifestationRole(models.TextChoices):
        TAKER = "taker", "Tomador"
        INTERMEDIARY = "intermediary", "Intermediario"

    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_manifestations")
    nfse_item = models.ForeignKey(NfseItem, verbose_name="NFS-e", on_delete=models.PROTECT, related_name="manifestations", null=True, blank=True)
    received_document = models.ForeignKey("NfseReceivedDocument", verbose_name="NFS-e recebida", on_delete=models.PROTECT, related_name="manifestations", null=True, blank=True)
    manifestation_type = models.CharField(verbose_name="Tipo", max_length=16, choices=ManifestationType.choices, db_index=True)
    manifestation_code = models.PositiveSmallIntegerField(verbose_name="Evento")
    manifestation_role = models.CharField(verbose_name="Manifestador", max_length=16, choices=ManifestationRole.choices, db_index=True)
    manifestor = models.PositiveSmallIntegerField(verbose_name="Codigo do manifestador")
    rejection_reason = models.PositiveSmallIntegerField(verbose_name="Motivo de rejeicao", null=True, blank=True)
    rejection_justification = models.CharField(verbose_name="Justificativa de rejeicao", max_length=255, blank=True, default="")
    request_payload = models.JSONField(verbose_name="Payload enviado", default=dict)
    response_payload = models.JSONField(verbose_name="Resposta remota", default=dict, blank=True)
    remote_uuid = models.UUIDField(verbose_name="UUID remoto da manifestacao", null=True, blank=True, db_index=True)
    remote_status = models.CharField(verbose_name="Status remoto", max_length=40, blank=True, default="")
    xml_manifestation = models.URLField(verbose_name="XML/artefato da manifestacao", blank=True, default="")
    status = models.CharField(max_length=20, choices=FiscalEmissionAttemptStatus.choices, default=FiscalEmissionAttemptStatus.STARTED, db_index=True)
    is_uncertain = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="nfse_manifestations")
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["nfse_item", "manifestation_code", "manifestor"],
                condition=models.Q(nfse_item__isnull=False, status__in=[FiscalEmissionAttemptStatus.STARTED, FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED, FiscalEmissionAttemptStatus.UNCERTAIN]),
                name="unique_active_nfse_manifestation",
            ),
            models.UniqueConstraint(
                fields=["received_document", "manifestation_code", "manifestor"],
                condition=models.Q(received_document__isnull=False, status__in=[FiscalEmissionAttemptStatus.STARTED, FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED, FiscalEmissionAttemptStatus.UNCERTAIN]),
                name="uniq_active_nfse_recv_man",
            ),
            models.CheckConstraint(
                condition=(models.Q(nfse_item__isnull=False, received_document__isnull=True) | models.Q(nfse_item__isnull=True, received_document__isnull=False)),
                name="nfse_manifest_single_origin",
            ),
        ]
        indexes = [
            models.Index(fields=["workshop", "status"], name="nfse_manifest_scope_status_idx"),
            models.Index(fields=["nfse_item", "manifestation_code", "manifestor"], name="nfse_manifest_item_type_idx"),
            models.Index(fields=["received_document", "manifestation_code", "manifestor"], name="nfse_man_recv_type_idx"),
        ]
        permissions = [
            ("issue_nfse_manifestation", "Pode manifestar NFS-e"),
            ("view_nfse_manifestation", "Pode visualizar manifestacao NFS-e"),
            ("download_nfse_manifestation", "Pode baixar documentos da manifestacao NFS-e"),
            ("view_nfse_manifestation_payload", "Pode visualizar payload da manifestacao NFS-e"),
        ]

    def clean(self) -> None:
        super().clean()
        if bool(self.nfse_item_id) == bool(self.received_document_id):
            raise ValidationError("A manifestacao NFS-e exige exatamente uma origem fiscal.")
        if self.nfse_item_id and self.nfse_item.workshop_id != self.workshop_id:
            raise ValidationError({"nfse_item": "A NFS-e pertence a outra oficina."})
        if self.received_document_id and self.received_document.workshop_id != self.workshop_id:
            raise ValidationError({"received_document": "A NFS-e recebida pertence a outra oficina."})
        if self.manifestation_type == self.ManifestationType.CONFIRMATION and self.manifestation_code != 1:
            raise ValidationError({"manifestation_code": "Confirmacao deve usar evento 1."})
        if self.manifestation_type == self.ManifestationType.REJECTION and self.manifestation_code != 2:
            raise ValidationError({"manifestation_code": "Rejeicao deve usar evento 2."})
        if self.manifestation_role == self.ManifestationRole.TAKER and self.manifestor != 1:
            raise ValidationError({"manifestor": "Tomador deve usar manifestador 1."})
        if self.manifestation_role == self.ManifestationRole.INTERMEDIARY and self.manifestor != 2:
            raise ValidationError({"manifestor": "Intermediario deve usar manifestador 2."})
        if self.manifestation_code == 1 and (self.rejection_reason or self.rejection_justification):
            raise ValidationError("Confirmacao nao deve conter motivo ou justificativa de rejeicao.")
        if self.manifestation_code == 2 and self.rejection_reason is None:
            raise ValidationError({"rejection_reason": "Rejeicao exige motivo."})
        if self.rejection_reason == 9 and not (15 <= len(self.rejection_justification.strip()) <= 255):
            raise ValidationError({"rejection_justification": "Motivo 9 exige justificativa entre 15 e 255 caracteres."})
        if self.rejection_reason not in (None, 9) and self.rejection_justification:
            raise ValidationError({"rejection_justification": "Justificativa deve ser enviada somente para motivo 9."})
        if self.is_uncertain != (self.status == FiscalEmissionAttemptStatus.UNCERTAIN):
            raise ValidationError("Status uncertain e marcador de incerteza devem permanecer consistentes.")

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = ("workshop_id", "nfse_item_id", "received_document_id", "manifestation_type", "manifestation_code", "manifestation_role", "manifestor", "rejection_reason", "rejection_justification", "request_payload")
            persisted = type(self).objects.filter(pk=self.pk).values(*immutable_fields).first()
            if persisted and any(persisted[field] != getattr(self, field) for field in immutable_fields):
                raise ValidationError("A intencao e o payload da manifestacao NFS-e sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        origin = self.nfse_item_id or f"received:{self.received_document_id}"
        return f"NfseManifestation[{origin}:{self.manifestation_code}:{self.status}]"


class NfseReceivedDocument(TimeStampedModel):
    class Source(models.TextChoices):
        XML_UPLOAD = "xml_upload", "Upload XML"

    class Role(models.TextChoices):
        TAKER = "taker", "Tomador"
        INTERMEDIARY = "intermediary", "Intermediario"
        PROVIDER = "provider", "Prestador"
        UNKNOWN = "unknown", "Desconhecido"
        MULTIPLE = "multiple", "Multiplos papeis"

    class ValidationStatus(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        VALIDATED = "validated", "Validado"
        REJECTED = "rejected", "Rejeitado"

    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_received_documents")
    company = models.ForeignKey(WebmaniaCompany, verbose_name="Empresa Webmania", on_delete=models.PROTECT, related_name="nfse_received_documents")
    source = models.CharField(verbose_name="Origem", max_length=24, choices=Source.choices, default=Source.XML_UPLOAD, db_index=True)
    xml_snapshot = models.TextField(verbose_name="XML original")
    xml_hash = models.CharField(verbose_name="Hash do XML", max_length=64, db_index=True)
    uuid = models.CharField(verbose_name="UUID remoto", max_length=64, blank=True, default="", db_index=True)
    access_key_or_identifier = models.CharField(verbose_name="Chave/identificador", max_length=80, blank=True, default="", db_index=True)
    verification_code = models.CharField(verbose_name="Codigo de verificacao", max_length=80, blank=True, default="")
    provider_tax_id = models.CharField(verbose_name="CPF/CNPJ prestador", max_length=14, blank=True, default="", db_index=True)
    taker_tax_id = models.CharField(verbose_name="CPF/CNPJ tomador", max_length=14, blank=True, default="", db_index=True)
    intermediary_tax_id = models.CharField(verbose_name="CPF/CNPJ intermediario", max_length=14, blank=True, default="", db_index=True)
    municipality_code = models.CharField(verbose_name="Codigo municipio", max_length=20, blank=True, default="")
    environment = models.CharField(verbose_name="Ambiente", max_length=1, blank=True, default="", choices=(("", "Nao informado"), ("1", "Producao"), ("2", "Homologacao")))
    issue_date = models.DateTimeField(verbose_name="Data de emissao", null=True, blank=True)
    service_amount = models.DecimalField(verbose_name="Valor do servico", max_digits=15, decimal_places=2, null=True, blank=True)
    status = models.CharField(verbose_name="Status local", max_length=20, default="received", db_index=True)
    remote_status = models.CharField(verbose_name="Status remoto", max_length=40, blank=True, default="")
    role = models.CharField(verbose_name="Papel da oficina", max_length=16, choices=Role.choices, default=Role.UNKNOWN, db_index=True)
    validation_status = models.CharField(verbose_name="Status de validacao", max_length=16, choices=ValidationStatus.choices, default=ValidationStatus.DRAFT, db_index=True)
    validation_errors = models.JSONField(verbose_name="Erros de validacao", default=list, blank=True)
    raw_payload = models.JSONField(verbose_name="Payload parseado", default=dict, blank=True)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="nfse_received_documents")

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "xml_hash"], name="unique_nfse_received_xml_hash_workshop"),
            models.UniqueConstraint(fields=["workshop", "uuid"], condition=~models.Q(uuid=""), name="unique_nfse_received_uuid_workshop"),
            models.UniqueConstraint(fields=["workshop", "access_key_or_identifier"], condition=~models.Q(access_key_or_identifier=""), name="unique_nfse_received_identifier_workshop"),
        ]
        indexes = [
            models.Index(fields=["workshop", "validation_status"], name="nfse_received_scope_status_idx"),
            models.Index(fields=["workshop", "role"], name="nfse_received_scope_role_idx"),
        ]
        permissions = [
            ("import_nfse_received", "Pode importar NFS-e recebida"),
            ("view_nfse_received", "Pode visualizar NFS-e recebida"),
            ("view_nfse_received_payload", "Pode visualizar payload da NFS-e recebida"),
            ("download_nfse_received_xml", "Pode baixar XML da NFS-e recebida"),
        ]

    @property
    def manifestation_eligible(self) -> bool:
        return self.validation_status == self.ValidationStatus.VALIDATED and self.role in {self.Role.TAKER, self.Role.INTERMEDIARY} and bool(self.uuid)

    @property
    def manifestation_block_reason(self) -> str:
        if self.validation_status != self.ValidationStatus.VALIDATED:
            return "Documento recebido ainda nao validado."
        if self.role == self.Role.PROVIDER:
            return "Oficina consta como prestadora; manifestacao futura e bloqueada."
        if self.role in {self.Role.UNKNOWN, self.Role.MULTIPLE}:
            return "Papel fiscal da oficina nao e seguro para manifestacao."
        if not self.uuid:
            return "Documento sem UUID remoto seguro."
        return ""

    def clean(self) -> None:
        super().clean()
        if self.company_id and self.workshop_id and self.company.workshop_id != self.workshop_id:
            raise ValidationError({"company": "A empresa Webmania pertence a outra oficina."})
        if self.source != self.Source.XML_UPLOAD:
            raise ValidationError({"source": "Nesta fase, somente upload manual de XML e permitido."})
        if not self.xml_snapshot.strip():
            raise ValidationError({"xml_snapshot": "XML obrigatorio."})
        if not self.xml_hash.strip():
            raise ValidationError({"xml_hash": "Hash do XML obrigatorio."})
        if self.validation_status == self.ValidationStatus.VALIDATED:
            if not (self.uuid or self.access_key_or_identifier or self.verification_code):
                raise ValidationError("NFS-e recebida validada exige UUID, chave/identificador ou codigo de verificacao.")
            if not (self.provider_tax_id or self.taker_tax_id or self.intermediary_tax_id):
                raise ValidationError("NFS-e recebida validada exige CPF/CNPJ fiscal extraido do XML.")
            if self.role in {self.Role.UNKNOWN, self.Role.MULTIPLE}:
                raise ValidationError("NFS-e recebida validada exige papel fiscal seguro.")

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = (
                "workshop_id",
                "company_id",
                "source",
                "xml_snapshot",
                "xml_hash",
                "uuid",
                "access_key_or_identifier",
                "verification_code",
                "provider_tax_id",
                "taker_tax_id",
                "intermediary_tax_id",
                "municipality_code",
                "environment",
                "issue_date",
                "service_amount",
                "remote_status",
                "role",
                "raw_payload",
            )
            persisted = type(self).objects.filter(pk=self.pk).values("validation_status", *immutable_fields).first()
            if persisted and persisted["validation_status"] == self.ValidationStatus.VALIDATED and any(persisted[field] != getattr(self, field) for field in immutable_fields):
                raise ValidationError("Os dados fiscais de uma NFS-e recebida validada sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        identifier = self.uuid or self.access_key_or_identifier or self.xml_hash[:12]
        return f"NfseReceivedDocument[{self.workshop_id}:{identifier}]"


class NfseReceivedDocumentConsultation(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_received_consultations")
    received_document = models.ForeignKey(NfseReceivedDocument, verbose_name="NFS-e recebida", on_delete=models.CASCADE, related_name="consultations")
    identifier = models.CharField(verbose_name="Identificador consultado", max_length=120, db_index=True)
    identifier_source = models.CharField(verbose_name="Origem do identificador", max_length=32)
    request_metadata = models.JSONField(verbose_name="Metadados da consulta", default=dict, blank=True)
    response_payload = models.JSONField(verbose_name="Resposta sanitizada", default=dict, blank=True)
    remote_status = models.CharField(verbose_name="Status remoto consultado", max_length=60, blank=True, default="")
    remote_uuid = models.CharField(verbose_name="UUID remoto consultado", max_length=64, blank=True, default="", db_index=True)
    remote_updated_at = models.DateTimeField(verbose_name="Atualizacao remota consultada", null=True, blank=True)
    national_standard_confirmed = models.BooleanField(verbose_name="Padrao Nacional confirmado pela consulta", null=True, blank=True)
    divergences = models.JSONField(verbose_name="Divergencias consultivas", default=list, blank=True)
    validation_errors = models.JSONField(verbose_name="Erros da consulta", default=list, blank=True)
    consulted_by = models.ForeignKey("accounts.User", verbose_name="Consultado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="nfse_received_consultations")

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["workshop", "received_document", "-criado_em"], name="nfse_recv_cons_doc_time_idx"),
            models.Index(fields=["workshop", "remote_uuid"], name="nfse_recv_cons_uuid_idx"),
        ]
        permissions = [
            ("consult_nfse_received", "Pode consultar NFS-e recebida na Webmania"),
            ("view_nfse_received_consultation", "Pode visualizar consultas de NFS-e recebida"),
            ("view_nfse_received_consultation_payload", "Pode visualizar payload de consulta de NFS-e recebida"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.received_document_id and self.workshop_id and self.received_document.workshop_id != self.workshop_id:
            raise ValidationError({"received_document": "A NFS-e recebida pertence a outra oficina."})
        if not str(self.identifier or "").strip():
            raise ValidationError({"identifier": "Informe o identificador consultado."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseReceivedDocumentConsultation[{self.received_document_id}:{self.identifier}]"


class NfseReceivedImportBatch(TimeStampedModel):
    class Source(models.TextChoices):
        XML_UPLOAD = "xml_upload", "Upload XML"

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processando"
        COMPLETED = "completed", "Concluido"
        COMPLETED_WITH_ERRORS = "completed_with_errors", "Concluido com erros"
        FAILED = "failed", "Falhou"

    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_received_import_batches")
    company = models.ForeignKey(WebmaniaCompany, verbose_name="Empresa Webmania", on_delete=models.PROTECT, related_name="nfse_received_import_batches")
    source = models.CharField(verbose_name="Origem", max_length=24, choices=Source.choices, default=Source.XML_UPLOAD, db_index=True)
    status = models.CharField(verbose_name="Status", max_length=32, choices=Status.choices, default=Status.PROCESSING, db_index=True)
    total_files = models.PositiveIntegerField(verbose_name="Total de arquivos", default=0)
    success_count = models.PositiveIntegerField(verbose_name="Importados", default=0)
    error_count = models.PositiveIntegerField(verbose_name="Erros", default=0)
    duplicate_count = models.PositiveIntegerField(verbose_name="Duplicados", default=0)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="nfse_received_import_batches")

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["workshop", "-criado_em"], name="nfse_recv_batch_time_idx"),
            models.Index(fields=["workshop", "status"], name="nfse_recv_batch_status_idx"),
        ]
        permissions = [
            ("import_nfse_received_batch", "Pode importar lote de XML de NFS-e recebida"),
            ("view_nfse_received_batch", "Pode visualizar lote de NFS-e recebida"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.company_id and self.workshop_id and self.company.workshop_id != self.workshop_id:
            raise ValidationError({"company": "A empresa Webmania pertence a outra oficina."})
        if self.source != self.Source.XML_UPLOAD:
            raise ValidationError({"source": "Nesta fase, somente lote local de XML e permitido."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseReceivedImportBatch[{self.workshop_id}:{self.status}:{self.total_files}]"


class NfseReceivedImportBatchItem(TimeStampedModel):
    class Status(models.TextChoices):
        IMPORTED = "imported", "Importado"
        REJECTED = "rejected", "Rejeitado"
        DUPLICATE = "duplicate", "Duplicado"
        INVALID_XML = "invalid_xml", "XML invalido"
        INVALID_TENANT = "invalid_tenant", "Oficina/CNPJ invalido"
        ERROR = "error", "Erro"

    batch = models.ForeignKey(NfseReceivedImportBatch, verbose_name="Lote", on_delete=models.CASCADE, related_name="items")
    filename = models.CharField(verbose_name="Arquivo", max_length=255)
    xml_hash = models.CharField(verbose_name="Hash do XML", max_length=64, blank=True, default="", db_index=True)
    status = models.CharField(verbose_name="Status", max_length=24, choices=Status.choices, db_index=True)
    received_document = models.ForeignKey(NfseReceivedDocument, verbose_name="NFS-e recebida", on_delete=models.SET_NULL, null=True, blank=True, related_name="batch_items")
    error_code = models.CharField(verbose_name="Codigo do erro", max_length=40, blank=True, default="")
    error_message = models.TextField(verbose_name="Mensagem do erro", blank=True, default="")
    validation_errors = models.JSONField(verbose_name="Erros de validacao", default=list, blank=True)
    raw_summary = models.JSONField(verbose_name="Resumo parseado", default=dict, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["batch", "status"], name="nfse_recv_bi_status_idx"),
            models.Index(fields=["batch", "xml_hash"], name="nfse_recv_bi_hash_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.received_document_id and self.batch_id and self.received_document.workshop_id != self.batch.workshop_id:
            raise ValidationError({"received_document": "A NFS-e recebida pertence a outra oficina."})
        if not self.filename.strip():
            raise ValidationError({"filename": "Informe o nome do arquivo."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseReceivedImportBatchItem[{self.batch_id}:{self.filename}:{self.status}]"


class NfseExternalXmlInbox(TimeStampedModel):
    class SourceType(models.TextChoices):
        MANUAL_UPLOAD = "manual_upload", "Upload manual"

    class Status(models.TextChoices):
        OPEN = "open", "Aberta"
        PARTIALLY_PROCESSED = "partially_processed", "Parcialmente processada"
        PROCESSED = "processed", "Processada"
        CLOSED = "closed", "Fechada"
        FAILED = "failed", "Falhou"

    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="nfse_external_xml_inboxes")
    company = models.ForeignKey(WebmaniaCompany, verbose_name="Empresa Webmania", on_delete=models.PROTECT, related_name="nfse_external_xml_inboxes")
    source_type = models.CharField(verbose_name="Tipo de origem", max_length=32, choices=SourceType.choices, default=SourceType.MANUAL_UPLOAD, db_index=True)
    source_label = models.CharField(verbose_name="Origem declarada", max_length=120, blank=True, default="")
    status = models.CharField(verbose_name="Status", max_length=32, choices=Status.choices, default=Status.OPEN, db_index=True)
    total_items = models.PositiveIntegerField(verbose_name="Total de itens", default=0)
    pending_count = models.PositiveIntegerField(verbose_name="Pendentes", default=0)
    approved_count = models.PositiveIntegerField(verbose_name="Aprovados", default=0)
    discarded_count = models.PositiveIntegerField(verbose_name="Descartados", default=0)
    processed_count = models.PositiveIntegerField(verbose_name="Processados", default=0)
    error_count = models.PositiveIntegerField(verbose_name="Erros", default=0)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="nfse_external_xml_inboxes")
    processed_by = models.ForeignKey("accounts.User", verbose_name="Processado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="processed_nfse_external_xml_inboxes")
    processed_at = models.DateTimeField(verbose_name="Processado em", null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["workshop", "-criado_em"], name="nfse_ext_inbox_time_idx"),
            models.Index(fields=["workshop", "status"], name="nfse_ext_inbox_status_idx"),
        ]
        permissions = [
            ("view_nfse_external_xml_inbox", "Pode visualizar inbox externa de XML NFS-e"),
            ("upload_nfse_external_xml_inbox", "Pode enviar XML para inbox externa NFS-e"),
            ("approve_nfse_external_xml_inbox", "Pode aprovar XML da inbox externa NFS-e"),
            ("process_nfse_external_xml_inbox", "Pode processar inbox externa de XML NFS-e"),
            ("discard_nfse_external_xml_inbox", "Pode descartar XML da inbox externa NFS-e"),
            ("view_nfse_external_xml_payload", "Pode visualizar XML da inbox externa NFS-e"),
            ("export_nfse_external_xml_inbox", "Pode exportar relatorio da inbox externa NFS-e"),
            ("bulk_manage_nfse_external_xml_inbox", "Pode executar acoes em massa na inbox externa NFS-e"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.company_id and self.workshop_id and self.company.workshop_id != self.workshop_id:
            raise ValidationError({"company": "A empresa Webmania pertence a outra oficina."})
        if self.source_type != self.SourceType.MANUAL_UPLOAD:
            raise ValidationError({"source_type": "Nesta fase, somente upload manual/assistido e permitido."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseExternalXmlInbox[{self.workshop_id}:{self.status}:{self.total_items}]"


class NfseExternalXmlInboxItem(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        INVALID = "invalid", "Invalido"
        DUPLICATE = "duplicate", "Duplicado"
        APPROVED = "approved", "Aprovado"
        DISCARDED = "discarded", "Descartado"
        PROCESSED = "processed", "Processado"
        ERROR = "error", "Erro"

    inbox = models.ForeignKey(NfseExternalXmlInbox, verbose_name="Inbox", on_delete=models.CASCADE, related_name="items")
    original_filename = models.CharField(verbose_name="Nome original", max_length=255)
    safe_filename = models.CharField(verbose_name="Nome seguro", max_length=255)
    content_type = models.CharField(verbose_name="Tipo de conteudo", max_length=120, blank=True, default="")
    xml_snapshot = models.TextField(verbose_name="XML candidato", blank=True, default="")
    xml_hash = models.CharField(verbose_name="Hash do XML", max_length=64, blank=True, default="", db_index=True)
    size_bytes = models.PositiveIntegerField(verbose_name="Tamanho em bytes", default=0)
    source_metadata = models.JSONField(verbose_name="Metadados da origem", default=dict, blank=True)
    status = models.CharField(verbose_name="Status", max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    validation_errors = models.JSONField(verbose_name="Erros de validacao", default=list, blank=True)
    parsed_summary = models.JSONField(verbose_name="Resumo parseado", default=dict, blank=True)
    discard_reason = models.TextField(verbose_name="Motivo de descarte", blank=True, default="")
    discarded_by = models.ForeignKey("accounts.User", verbose_name="Descartado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="discarded_nfse_external_xml_items")
    discarded_at = models.DateTimeField(verbose_name="Descartado em", null=True, blank=True)
    approved_by = models.ForeignKey("accounts.User", verbose_name="Aprovado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_nfse_external_xml_items")
    approved_at = models.DateTimeField(verbose_name="Aprovado em", null=True, blank=True)
    processed_by = models.ForeignKey("accounts.User", verbose_name="Processado por", on_delete=models.SET_NULL, null=True, blank=True, related_name="processed_nfse_external_xml_items")
    processed_at = models.DateTimeField(verbose_name="Processado em", null=True, blank=True)
    linked_batch = models.ForeignKey(NfseReceivedImportBatch, verbose_name="Lote vinculado", on_delete=models.SET_NULL, null=True, blank=True, related_name="external_inbox_items")
    linked_batch_item = models.ForeignKey(NfseReceivedImportBatchItem, verbose_name="Item de lote vinculado", on_delete=models.SET_NULL, null=True, blank=True, related_name="external_inbox_items")
    linked_received_document = models.ForeignKey(NfseReceivedDocument, verbose_name="NFS-e recebida vinculada", on_delete=models.SET_NULL, null=True, blank=True, related_name="external_inbox_items")

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["inbox", "status"], name="nfse_ext_item_status_idx"),
            models.Index(fields=["inbox", "xml_hash"], name="nfse_ext_item_hash_idx"),
            models.Index(fields=["status", "xml_hash"], name="nfse_ext_active_hash_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.original_filename.strip():
            raise ValidationError({"original_filename": "Informe o nome original."})
        if not self.safe_filename.strip():
            raise ValidationError({"safe_filename": "Informe o nome seguro."})
        if self.linked_batch_id and self.inbox_id and self.linked_batch.workshop_id != self.inbox.workshop_id:
            raise ValidationError({"linked_batch": "O lote pertence a outra oficina."})
        if self.linked_batch_item_id and self.linked_batch_id and self.linked_batch_item.batch_id != self.linked_batch_id:
            raise ValidationError({"linked_batch_item": "O item de lote nao pertence ao lote vinculado."})
        if self.linked_received_document_id and self.inbox_id and self.linked_received_document.workshop_id != self.inbox.workshop_id:
            raise ValidationError({"linked_received_document": "A NFS-e recebida pertence a outra oficina."})
        if self.status in {self.Status.PENDING, self.Status.APPROVED, self.Status.PROCESSED} and not self.xml_snapshot.strip():
            raise ValidationError({"xml_snapshot": "XML candidato obrigatorio para item ativo."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"NfseExternalXmlInboxItem[{self.inbox_id}:{self.safe_filename}:{self.status}]"


class NfeItem(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE)
    request = models.ForeignKey(NfeRequest, verbose_name="Requisição de NF-e", related_name="items", on_delete=models.SET_NULL, null=True)
    uuid = models.UUIDField(db_index=True)
    model = models.CharField(max_length=255, default="nfe")
    status = models.CharField(max_length=20, choices=NfeItemStatus.choices, default=NfeItemStatus.processando)
    reason = models.TextField(blank=True, default="")
    number = models.CharField(max_length=40, blank=True, default="")
    series = models.CharField(max_length=20, blank=True, default="")
    receipt = models.CharField(max_length=40, blank=True, default="")
    access_key = models.CharField(max_length=60, blank=True, default="")
    xml_url = models.URLField(blank=True, default="")
    danfe_url = models.URLField(blank=True, default="")
    danfe_simple_url = models.URLField(blank=True, default="")
    danfe_label_url = models.URLField(blank=True, default="")
    log_payload = models.JSONField(blank=True, default=dict)
    raw_payload = models.JSONField(blank=True, default=dict)
    last_webhook_at = models.DateTimeField(null=True, blank=True)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workorder", "uuid"], name="unique_nfe_item_per_workorder"),
        ]

        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]


class FiscalDocument(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="fiscal_documents")
    account = models.ForeignKey("accounts.Account", verbose_name="Conta", on_delete=models.PROTECT, null=True, blank=True, related_name="fiscal_documents")
    document_type = models.CharField(max_length=12, choices=FiscalDocumentType.choices, default=FiscalDocumentType.NFE, db_index=True)
    origin = models.CharField(max_length=16, choices=FiscalDocumentOrigin.choices, default=FiscalDocumentOrigin.LOCAL, db_index=True)
    purpose = models.CharField(max_length=24, choices=FiscalDocumentPurpose.choices, default=FiscalDocumentPurpose.NORMAL, db_index=True)
    complementary_type = models.CharField(max_length=32, choices=FiscalDocumentComplementaryType.choices, blank=True, default="", db_index=True)
    fiscal_purpose_type = models.CharField(max_length=8, blank=True, default="", db_index=True)
    legacy_nfe_item = models.OneToOneField(NfeItem, verbose_name="Item legado NF-e", on_delete=models.CASCADE, null=True, blank=True, related_name="fiscal_document")
    referenced_basis = models.ForeignKey("FiscalReferencedBasis", verbose_name="Base fiscal referenciada", on_delete=models.PROTECT, null=True, blank=True, related_name="derived_documents")
    credit_product_preview = models.OneToOneField("FiscalCreditProductPreview", verbose_name="Previa fiscal de credito", on_delete=models.PROTECT, null=True, blank=True, related_name="credit_document")
    debit_product_preview = models.OneToOneField("FiscalDebitProductPreview", verbose_name="Previa fiscal de debito", on_delete=models.PROTECT, null=True, blank=True, related_name="debit_document")
    remote_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    access_key = models.CharField(max_length=80, blank=True, default="", db_index=True)
    series = models.CharField(max_length=20, blank=True, default="")
    number = models.CharField(max_length=40, blank=True, default="")
    receipt = models.CharField(max_length=40, blank=True, default="")
    environment = models.CharField(max_length=10, blank=True, default="")
    status = models.CharField(max_length=20, choices=FiscalDocumentStatus.choices, default=FiscalDocumentStatus.PROCESSING, db_index=True)
    remote_status = models.CharField(max_length=40, blank=True, default="")
    request_payload = models.JSONField(blank=True, default=dict)
    response_payload = models.JSONField(blank=True, default=dict)
    xml_url = models.URLField(blank=True, default="")
    danfe_url = models.URLField(blank=True, default="")
    requested_by = models.ForeignKey("accounts.User", verbose_name="Solicitante", on_delete=models.SET_NULL, null=True, blank=True, related_name="requested_fiscal_documents")
    external_confirmation = models.BooleanField(default=False)
    external_confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "legacy_nfe_item"], name="unique_fiscal_document_per_legacy_nfe_item"),
            models.UniqueConstraint(fields=["workshop", "document_type", "remote_uuid"], condition=~models.Q(remote_uuid=""), name="unique_fiscal_document_remote_uuid_per_workshop"),
            models.UniqueConstraint(fields=["workshop", "document_type", "access_key"], condition=~models.Q(access_key=""), name="unique_fiscal_document_access_key_per_workshop"),
            models.CheckConstraint(condition=~models.Q(purpose=FiscalDocumentPurpose.CREDIT) | models.Q(origin=FiscalDocumentOrigin.DERIVED, fiscal_purpose_type="1", referenced_basis__isnull=False, credit_product_preview__isnull=False), name="fiscal_credit_document_requires_basis_preview"),
            models.CheckConstraint(condition=~models.Q(purpose=FiscalDocumentPurpose.DEBIT) | models.Q(origin=FiscalDocumentOrigin.DERIVED, fiscal_purpose_type="4", referenced_basis__isnull=False, debit_product_preview__isnull=False), name="fiscal_debit_document_requires_basis_preview"),
        ]
        indexes = [
            models.Index(fields=["workshop", "document_type", "status"]),
            models.Index(fields=["legacy_nfe_item"]),
            models.Index(fields=["workshop", "document_type", "origin", "purpose"]),
            models.Index(fields=["workshop", "document_type", "purpose", "complementary_type"]),
            models.Index(fields=["workshop", "document_type", "purpose", "fiscal_purpose_type"]),
        ]
        permissions = [
            ("issue_nfe_return", "Pode emitir NF-e de devolucao"),
            ("issue_nfe_reversal", "Pode emitir NF-e de estorno"),
            ("download_nfe_return", "Pode baixar XML/DANFE de NF-e de devolucao ou estorno"),
            ("view_nfe_return_payload", "Pode visualizar payload de NF-e de devolucao ou estorno"),
            ("issue_nfe_complementary_price_quantity", "Pode emitir NF-e complementar de preco/quantidade"),
            ("view_nfe_complementary", "Pode visualizar NF-e complementar"),
            ("download_nfe_complementary", "Pode baixar XML/DANFE de NF-e complementar"),
            ("view_nfe_complementary_payload", "Pode visualizar payload de NF-e complementar"),
            ("issue_nfe_adjustment", "Pode emitir NF-e de ajuste"),
            ("view_nfe_adjustment", "Pode visualizar NF-e de ajuste"),
            ("download_nfe_adjustment", "Pode baixar XML/DANFE de NF-e de ajuste"),
            ("view_nfe_adjustment_payload", "Pode visualizar payload de NF-e de ajuste"),
            ("issue_nfce", "Pode emitir NFC-e"),
            ("view_nfce", "Pode visualizar NFC-e"),
            ("download_nfce", "Pode baixar XML/DANFE de NFC-e"),
            ("view_nfce_payload", "Pode visualizar payload de NFC-e"),
            ("cancel_nfce", "Pode cancelar NFC-e"),
            ("issue_nfe_credit", "Pode emitir NF-e de credito"),
            ("view_nfe_credit", "Pode visualizar NF-e de credito"),
            ("download_nfe_credit", "Pode baixar XML/DANFE de NF-e de credito"),
            ("view_nfe_credit_payload", "Pode visualizar payload de NF-e de credito"),
            ("cancel_nfe_credit", "Pode cancelar NF-e de credito"),
            ("issue_nfe_debit", "Pode emitir NF-e de debito"),
            ("view_nfe_debit", "Pode visualizar NF-e de debito"),
            ("download_nfe_debit", "Pode baixar XML/DANFE de NF-e de debito"),
            ("view_nfe_debit_payload", "Pode visualizar payload de NF-e de debito"),
            ("cancel_nfe_debit", "Pode cancelar NF-e de debito"),
        ]

    def __str__(self) -> str:
        return f"FiscalDocument[{self.document_type}:{self.number or self.access_key or self.remote_uuid or self.pk}]"


class FiscalDocumentLink(TimeStampedModel):
    document = models.ForeignKey(FiscalDocument, verbose_name="Documento derivado", on_delete=models.CASCADE, related_name="links_from")
    related_document = models.ForeignKey(FiscalDocument, verbose_name="Documento original", on_delete=models.CASCADE, related_name="links_to")
    role = models.CharField(max_length=24, choices=FiscalDocumentLinkRole.choices, db_index=True)
    metadata = models.JSONField(blank=True, default=dict)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["document", "related_document", "role"], name="unique_fiscal_document_link_role"),
        ]
        indexes = [
            models.Index(fields=["related_document", "role"]),
            models.Index(fields=["document", "role"]),
        ]

    def __str__(self) -> str:
        return f"FiscalDocumentLink[{self.document_id}->{self.related_document_id}:{self.role}]"


class FiscalReferencedBasis(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="fiscal_referenced_bases")
    source_document = models.ForeignKey(FiscalDocument, verbose_name="Documento fiscal de origem", on_delete=models.PROTECT, null=True, blank=True, related_name="referenced_bases")
    source_nfe_item = models.ForeignKey(NfeItem, verbose_name="NF-e legada de origem", on_delete=models.PROTECT, null=True, blank=True, related_name="referenced_bases")
    source_access_key = models.CharField(verbose_name="Chave de acesso de origem", max_length=44, blank=True, default="", db_index=True)
    source_item_sequence = models.PositiveSmallIntegerField(verbose_name="Sequencial fiscal do item")
    source_document_type = models.CharField(verbose_name="Tipo do documento de origem", max_length=12, choices=FiscalDocumentType.choices, default=FiscalDocumentType.NFE)
    basis_type = models.CharField(verbose_name="Tipo da base", max_length=12, choices=FiscalReferencedBasisType.choices, db_index=True)
    fiscal_hypothesis = models.CharField(verbose_name="Hipotese fiscal", max_length=48, choices=FiscalHypothesis.choices, db_index=True)
    ibs_cbs_snapshot = models.JSONField(verbose_name="Snapshot IBS/CBS", default=dict)
    financial_reference = models.ForeignKey("finance.FinancialMovement", verbose_name="Movimentacao financeira", on_delete=models.PROTECT, null=True, blank=True, related_name="fiscal_referenced_bases")
    stock_reference = models.ForeignKey("stock.StockMovement", verbose_name="Movimentacao de estoque", on_delete=models.PROTECT, null=True, blank=True, related_name="fiscal_referenced_bases")
    external_origin = models.BooleanField(verbose_name="Origem externa", default=False)
    external_xml_validated = models.BooleanField(verbose_name="XML externo validado", default=False)
    status = models.CharField(verbose_name="Status", max_length=16, choices=FiscalReferencedBasisStatus.choices, default=FiscalReferencedBasisStatus.DRAFT, db_index=True)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_fiscal_referenced_bases")
    approved_by = models.ForeignKey("accounts.User", verbose_name="Aprovada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_fiscal_referenced_bases")
    approved_at = models.DateTimeField(verbose_name="Aprovada em", null=True, blank=True)
    notes = models.TextField(verbose_name="Evidencias e observacoes", blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "source_document", "source_item_sequence", "fiscal_hypothesis"], condition=models.Q(source_document__isnull=False), name="unique_local_fiscal_referenced_basis"),
            models.UniqueConstraint(fields=["workshop", "source_access_key", "source_item_sequence", "fiscal_hypothesis"], condition=models.Q(external_origin=True) & ~models.Q(source_access_key=""), name="unique_external_fiscal_referenced_basis"),
        ]
        indexes = [
            models.Index(fields=["workshop", "status", "basis_type"], name="fiscal_basis_scope_status_idx"),
            models.Index(fields=["source_document", "source_item_sequence"], name="fiscal_basis_source_item_idx"),
        ]
        permissions = [
            ("prepare_nfe_credit_debit_basis", "Pode preparar base fiscal de credito/debito"),
            ("approve_nfe_credit_debit_basis", "Pode aprovar base fiscal de credito/debito"),
            ("view_nfe_credit_debit_basis", "Pode visualizar base fiscal de credito/debito"),
            ("view_nfe_credit_debit_basis_payload", "Pode visualizar payload da base fiscal de credito/debito"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.source_item_sequence <= 0 or self.source_item_sequence > 999:
            raise ValidationError({"source_item_sequence": "O sequencial fiscal deve estar entre 1 e 999."})
        if self.source_document_id and self.source_document.workshop_id != self.workshop_id:
            raise ValidationError({"source_document": "O documento fiscal pertence a outra oficina."})
        if self.source_nfe_item_id and self.source_nfe_item.workshop_id != self.workshop_id:
            raise ValidationError({"source_nfe_item": "A NF-e de origem pertence a outra oficina."})
        if self.source_document_id and self.source_document_type != self.source_document.document_type:
            raise ValidationError({"source_document_type": "O tipo informado nao corresponde ao documento fiscal de origem."})
        if self.source_document_id and self.source_nfe_item_id and self.source_document.legacy_nfe_item_id != self.source_nfe_item_id:
            raise ValidationError({"source_nfe_item": "A NF-e legada nao corresponde ao documento fiscal de origem."})
        if self.financial_reference_id and self.financial_reference.workshop_id != self.workshop_id:
            raise ValidationError({"financial_reference": "A movimentacao financeira pertence a outra oficina."})
        if self.stock_reference_id and self.stock_reference.workshop_id != self.workshop_id:
            raise ValidationError({"stock_reference": "A movimentacao de estoque pertence a outra oficina."})
        expected_basis_type = FiscalReferencedBasisType.CREDIT if self.fiscal_hypothesis.startswith("credit_") else FiscalReferencedBasisType.DEBIT if self.fiscal_hypothesis.startswith("debit_") else ""
        if not expected_basis_type or self.basis_type != expected_basis_type:
            raise ValidationError({"basis_type": "O tipo da base nao corresponde a hipotese fiscal."})
        if not self.external_origin and self.source_document_id is None:
            raise ValidationError({"source_document": "Base de origem local exige documento fiscal de origem."})
        if not self.external_origin and self.source_document_id and self.source_document.origin != FiscalDocumentOrigin.LOCAL:
            raise ValidationError({"source_document": "Base local exige documento fiscal de origem local."})
        if self.external_origin and self.source_document_id and self.source_document.origin != FiscalDocumentOrigin.EXTERNAL:
            raise ValidationError({"source_document": "Base externa exige projecao fiscal de origem externa."})
        if self.external_origin and len("".join(char for char in self.source_access_key if char.isdigit())) != 44:
            raise ValidationError({"source_access_key": "Base externa exige chave de acesso com 44 digitos."})
        if self.external_origin and not self.external_xml_validated and self.status == FiscalReferencedBasisStatus.APPROVED:
            raise ValidationError("Documento externo sem XML/importacao validada nao pode ser aprovado.")

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = (
                "source_document_id",
                "source_nfe_item_id",
                "source_access_key",
                "source_item_sequence",
                "source_document_type",
                "basis_type",
                "fiscal_hypothesis",
                "ibs_cbs_snapshot",
                "financial_reference_id",
                "stock_reference_id",
                "external_origin",
                "external_xml_validated",
            )
            persisted = type(self).objects.filter(pk=self.pk).values("status", *immutable_fields).first()
            if persisted and persisted["status"] == FiscalReferencedBasisStatus.APPROVED and any(persisted[field] != getattr(self, field) for field in immutable_fields):
                raise ValidationError("A origem, hipotese e os snapshots de uma base aprovada sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"FiscalReferencedBasis[{self.fiscal_hypothesis}:{self.source_access_key}:{self.source_item_sequence}]"


class FiscalReferencedBasisItem(TimeStampedModel):
    basis = models.OneToOneField(FiscalReferencedBasis, verbose_name="Base fiscal", on_delete=models.CASCADE, related_name="commercial_item")
    source_item_sequence = models.PositiveSmallIntegerField(verbose_name="Sequencial fiscal do item")
    source_item_description = models.CharField(verbose_name="Descricao fiscal do item", max_length=255, blank=True, default="")
    source_item_code = models.CharField(verbose_name="Codigo fiscal do item", max_length=80, blank=True, default="")
    source_item_ncm = models.CharField(verbose_name="NCM fiscal do item", max_length=8, blank=True, default="")
    source_item_cfop = models.CharField(verbose_name="CFOP fiscal do item", max_length=4, blank=True, default="")
    source_quantity = models.DecimalField(verbose_name="Quantidade fiscal", max_digits=18, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    source_unit = models.CharField(verbose_name="Unidade fiscal", max_length=12, blank=True, default="")
    source_unit_price = models.DecimalField(verbose_name="Valor unitario fiscal", max_digits=18, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    source_total_amount = models.DecimalField(verbose_name="Valor total fiscal", max_digits=18, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    principal_amount = models.DecimalField(verbose_name="Valor principal", max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    fine_amount = models.DecimalField(verbose_name="Valor de multa", max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    interest_amount = models.DecimalField(verbose_name="Valor de juros", max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    other_amount = models.DecimalField(verbose_name="Outros valores", max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    credit_debit_base_amount = models.DecimalField(verbose_name="Base monetaria credito/debito", max_digits=18, decimal_places=2, default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))])
    commercial_snapshot = models.JSONField(verbose_name="Snapshot comercial", default=dict)
    monetary_snapshot = models.JSONField(verbose_name="Snapshot monetario", default=dict)

    class Meta(TimeStampedModel.Meta):
        indexes = [models.Index(fields=["source_item_cfop", "source_item_ncm"], name="fiscal_basis_item_tax_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(source_quantity__isnull=True) | models.Q(source_quantity__gte=0), name="fiscal_basis_item_quantity_nonnegative"),
            models.CheckConstraint(condition=models.Q(source_unit_price__isnull=True) | models.Q(source_unit_price__gte=0), name="fiscal_basis_item_unit_price_nonnegative"),
            models.CheckConstraint(condition=models.Q(source_total_amount__isnull=True) | models.Q(source_total_amount__gte=0), name="fiscal_basis_item_total_nonnegative"),
            models.CheckConstraint(condition=models.Q(principal_amount__gte=0) & models.Q(fine_amount__gte=0) & models.Q(interest_amount__gte=0) & models.Q(other_amount__gte=0) & models.Q(credit_debit_base_amount__gte=0), name="fiscal_basis_item_money_nonnegative"),
        ]

    @property
    def expected_base_amount(self) -> Decimal:
        if self.basis.fiscal_hypothesis in {FiscalHypothesis.CREDIT_FINE_INTEREST, FiscalHypothesis.DEBIT_FINE_INTEREST}:
            return (self.fine_amount + self.interest_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (self.principal_amount + self.fine_amount + self.interest_amount + self.other_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def approval_errors(self) -> list[str]:
        errors: list[str] = []
        required_text = {
            "descricao": self.source_item_description,
            "NCM": self.source_item_ncm,
            "CFOP": self.source_item_cfop,
            "unidade": self.source_unit,
        }
        errors.extend(label for label, value in required_text.items() if not str(value or "").strip())
        if self.source_quantity is None or self.source_quantity <= 0:
            errors.append("quantidade")
        if self.source_unit_price is None or self.source_unit_price < 0:
            errors.append("valor unitario")
        if self.source_total_amount is None or self.source_total_amount < 0:
            errors.append("valor total")
        if not self.commercial_snapshot:
            errors.append("snapshot comercial")
        if self.credit_debit_base_amount <= 0:
            errors.append("base monetaria positiva")
        return errors

    def clean(self) -> None:
        super().clean()
        if self.basis_id and self.source_item_sequence != self.basis.source_item_sequence:
            raise ValidationError({"source_item_sequence": "O sequencial deve corresponder ao item da base fiscal."})
        if self.source_item_ncm and (len(self.source_item_ncm) != 8 or not self.source_item_ncm.isdigit()):
            raise ValidationError({"source_item_ncm": "O NCM deve possuir 8 digitos."})
        if self.source_item_cfop and (len(self.source_item_cfop) != 4 or not self.source_item_cfop.isdigit()):
            raise ValidationError({"source_item_cfop": "O CFOP deve possuir 4 digitos."})
        if self.source_quantity is not None and self.source_unit_price is not None and self.source_total_amount is not None:
            calculated = (self.source_quantity * self.source_unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if abs(calculated - self.source_total_amount) > Decimal("0.01"):
                raise ValidationError({"source_total_amount": "Quantidade x valor unitario diverge do total fiscal alem da tolerancia de R$ 0,01."})
        if self.credit_debit_base_amount != self.expected_base_amount:
            raise ValidationError({"credit_debit_base_amount": "A base monetaria nao corresponde a composicao explicita da hipotese fiscal."})
        if self.basis_id and self.basis.status == FiscalReferencedBasisStatus.APPROVED:
            missing = self.approval_errors()
            if missing:
                raise ValidationError(f"Base aprovada possui dados incompletos: {', '.join(missing)}.")

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            persisted = type(self).objects.filter(pk=self.pk).values().first()
            if persisted and self.basis.status == FiscalReferencedBasisStatus.APPROVED:
                immutable_fields = (
                    "source_item_sequence",
                    "source_item_description",
                    "source_item_code",
                    "source_item_ncm",
                    "source_item_cfop",
                    "source_quantity",
                    "source_unit",
                    "source_unit_price",
                    "source_total_amount",
                    "principal_amount",
                    "fine_amount",
                    "interest_amount",
                    "other_amount",
                    "credit_debit_base_amount",
                    "commercial_snapshot",
                    "monetary_snapshot",
                )
                if any(persisted[field] != getattr(self, field) for field in immutable_fields):
                    raise ValidationError("Os snapshots comercial e monetario de uma base aprovada sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"FiscalReferencedBasisItem[{self.basis_id}:{self.source_item_sequence}]"


class FiscalCreditProductPreview(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="fiscal_credit_product_previews")
    basis = models.ForeignKey(FiscalReferencedBasis, verbose_name="Base fiscal", on_delete=models.PROTECT, related_name="credit_product_previews")
    basis_item = models.ForeignKey(FiscalReferencedBasisItem, verbose_name="Item da base", on_delete=models.PROTECT, related_name="credit_product_previews")
    revision = models.PositiveSmallIntegerField(verbose_name="Revisao", default=1)
    operation_type = models.CharField(verbose_name="Tipo da operacao", max_length=12, default="credit")
    fiscal_purpose_type = models.CharField(verbose_name="Tipo fiscal remoto", max_length=4, default="1")
    source_access_key = models.CharField(verbose_name="Chave da NF-e referenciada", max_length=44, db_index=True)
    source_item_sequence = models.PositiveSmallIntegerField(verbose_name="Sequencial fiscal do item")
    product_cfop = models.CharField(verbose_name="CFOP validado", max_length=4)
    product_quantity = models.DecimalField(verbose_name="Quantidade explicita", max_digits=18, decimal_places=6, validators=[MinValueValidator(Decimal("0.000001"))])
    product_unit_price = models.DecimalField(verbose_name="Valor unitario explicito", max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    product_total_amount = models.DecimalField(verbose_name="Total explicito", max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    product_payload = models.JSONField(verbose_name="Produto fiscal validado", default=dict)
    ibs_cbs_payload = models.JSONField(verbose_name="IBS/CBS historico", default=dict)
    preview_payload = models.JSONField(verbose_name="Pre-payload futuro", default=dict)
    forbidden_tax_groups_detected = models.JSONField(verbose_name="Grupos tributarios proibidos", default=list, blank=True)
    validation_status = models.CharField(verbose_name="Status", max_length=16, choices=FiscalProductPreviewStatus.choices, default=FiscalProductPreviewStatus.DRAFT, db_index=True)
    validation_errors = models.JSONField(verbose_name="Erros de validacao", default=list, blank=True)
    explicit_value_confirmation = models.BooleanField(verbose_name="Valores informados explicitamente", default=False)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_fiscal_credit_product_previews")
    approved_by = models.ForeignKey("accounts.User", verbose_name="Aprovada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_fiscal_credit_product_previews")
    approved_at = models.DateTimeField(verbose_name="Aprovada em", null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["basis", "revision"], name="unique_fiscal_credit_preview_revision"),
            models.CheckConstraint(condition=models.Q(product_quantity__gt=0), name="fiscal_credit_preview_quantity_positive"),
            models.CheckConstraint(condition=models.Q(product_unit_price__gt=0), name="fiscal_credit_preview_unit_price_positive"),
            models.CheckConstraint(condition=models.Q(product_total_amount__gt=0), name="fiscal_credit_preview_total_positive"),
        ]
        indexes = [
            models.Index(fields=["workshop", "validation_status"], name="fisc_credit_prev_scope_idx"),
            models.Index(fields=["source_access_key", "source_item_sequence"], name="fisc_credit_prev_source_idx"),
        ]
        permissions = [
            ("prepare_nfe_credit_product_preview", "Pode preparar previa de produto de credito"),
            ("approve_nfe_credit_product_preview", "Pode aprovar previa de produto de credito"),
            ("view_nfe_credit_product_preview", "Pode visualizar previa de produto de credito"),
            ("view_nfe_credit_product_preview_payload", "Pode visualizar payload da previa de produto de credito"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.basis_id and self.basis.workshop_id != self.workshop_id:
            raise ValidationError({"basis": "A base pertence a outra oficina."})
        if self.basis_item_id and self.basis_item.basis_id != self.basis_id:
            raise ValidationError({"basis_item": "O item nao pertence a base informada."})
        if self.basis_id and self.basis.status != FiscalReferencedBasisStatus.APPROVED:
            raise ValidationError({"basis": "A previa exige base fiscal aprovada."})
        if self.basis_id and self.basis.fiscal_hypothesis != FiscalHypothesis.CREDIT_FINE_INTEREST:
            raise ValidationError({"basis": "A previa exige hipotese de credito por multa/juros."})
        if self.basis_id and self.basis.external_origin and not self.basis.external_xml_validated:
            raise ValidationError({"basis": "Documento externo exige XML/importacao validada."})
        if self.operation_type != "credit" or self.fiscal_purpose_type != "1":
            raise ValidationError("A previa atual suporta somente credito tipo 1.")
        if self.source_item_sequence != self.basis.source_item_sequence:
            raise ValidationError({"source_item_sequence": "Sequencial divergente da base aprovada."})
        if len(self.source_access_key) != 44 or not self.source_access_key.isdigit():
            raise ValidationError({"source_access_key": "A chave referenciada deve possuir 44 digitos."})
        if len(self.product_cfop) != 4 or not self.product_cfop.isdigit():
            raise ValidationError({"product_cfop": "O CFOP deve possuir 4 digitos."})
        calculated = (self.product_quantity * self.product_unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(calculated - self.product_total_amount) > Decimal("0.01"):
            raise ValidationError({"product_total_amount": "Quantidade x valor unitario diverge do total alem da tolerancia de R$ 0,01."})
        if self.product_total_amount != self.basis_item.credit_debit_base_amount:
            raise ValidationError({"product_total_amount": "O total deve ser exatamente igual a multa + juros da base aprovada."})
        if not self.explicit_value_confirmation:
            raise ValidationError({"explicit_value_confirmation": "Confirme que quantidade, valor unitario, total e CFOP foram definidos explicitamente."})
        required_ibs = ("situacao_tributaria", "classificacao_tributaria")
        missing_ibs = [field for field in required_ibs if not str(self.ibs_cbs_payload.get(field) or "").strip()]
        if missing_ibs:
            raise ValidationError({"ibs_cbs_payload": f"IBS/CBS incompleto: {', '.join(missing_ibs)}."})
        if self.forbidden_tax_groups_detected:
            raise ValidationError({"forbidden_tax_groups_detected": "A previa contem grupos tributarios proibidos."})
        required_product = ("nome", "ncm", "quantidade", "unidade", "subtotal", "total", "codigo_cfop", "impostos")
        missing_product = [field for field in required_product if self.product_payload.get(field) in (None, "", {})]
        if missing_product:
            raise ValidationError({"product_payload": f"Produto fiscal incompleto: {', '.join(missing_product)}."})
        if self.validation_status == FiscalProductPreviewStatus.APPROVED and self.validation_errors:
            raise ValidationError({"validation_errors": "Previa com erros nao pode ser aprovada."})

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = (
                "workshop_id",
                "basis_id",
                "basis_item_id",
                "revision",
                "operation_type",
                "fiscal_purpose_type",
                "source_access_key",
                "source_item_sequence",
                "product_cfop",
                "product_quantity",
                "product_unit_price",
                "product_total_amount",
                "product_payload",
                "ibs_cbs_payload",
                "preview_payload",
                "forbidden_tax_groups_detected",
                "explicit_value_confirmation",
            )
            persisted = type(self).objects.filter(pk=self.pk).values("validation_status", *immutable_fields).first()
            if persisted and persisted["validation_status"] == FiscalProductPreviewStatus.APPROVED and any(persisted[field] != getattr(self, field) for field in immutable_fields):
                raise ValidationError("Os payloads e valores de uma previa aprovada sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"FiscalCreditProductPreview[{self.basis_id}:r{self.revision}]"


class FiscalDebitProductPreview(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="fiscal_debit_product_previews")
    basis = models.ForeignKey(FiscalReferencedBasis, verbose_name="Base fiscal", on_delete=models.PROTECT, related_name="debit_product_previews")
    basis_item = models.ForeignKey(FiscalReferencedBasisItem, verbose_name="Item da base", on_delete=models.PROTECT, related_name="debit_product_previews")
    revision = models.PositiveSmallIntegerField(verbose_name="Revisao", default=1)
    operation_type = models.CharField(verbose_name="Tipo da operacao", max_length=12, default="debit")
    fiscal_purpose_type = models.CharField(verbose_name="Tipo fiscal remoto", max_length=4, default="4")
    source_access_key = models.CharField(verbose_name="Chave do DF-e referenciado", max_length=44, db_index=True)
    source_item_sequence = models.PositiveSmallIntegerField(verbose_name="Sequencial fiscal do item")
    dfe_referenciado = models.JSONField(verbose_name="DF-e referenciado", default=dict)
    product_cfop = models.CharField(verbose_name="CFOP validado", max_length=4)
    product_quantity = models.DecimalField(verbose_name="Quantidade explicita", max_digits=18, decimal_places=6, validators=[MinValueValidator(Decimal("0.000001"))])
    product_unit_price = models.DecimalField(verbose_name="Valor unitario explicito", max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    product_total_amount = models.DecimalField(verbose_name="Total explicito", max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    product_payload = models.JSONField(verbose_name="Produto fiscal validado", default=dict)
    ibs_cbs_payload = models.JSONField(verbose_name="IBS/CBS historico", default=dict)
    preview_payload = models.JSONField(verbose_name="Pre-payload futuro", default=dict)
    forbidden_tax_groups_detected = models.JSONField(verbose_name="Grupos tributarios proibidos", default=list, blank=True)
    validation_status = models.CharField(verbose_name="Status", max_length=16, choices=FiscalProductPreviewStatus.choices, default=FiscalProductPreviewStatus.DRAFT, db_index=True)
    validation_errors = models.JSONField(verbose_name="Erros de validacao", default=list, blank=True)
    explicit_value_confirmation = models.BooleanField(verbose_name="Valores informados explicitamente", default=False)
    created_by = models.ForeignKey("accounts.User", verbose_name="Criada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="created_fiscal_debit_product_previews")
    approved_by = models.ForeignKey("accounts.User", verbose_name="Aprovada por", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_fiscal_debit_product_previews")
    approved_at = models.DateTimeField(verbose_name="Aprovada em", null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["basis", "revision"], name="fisc_debit_prev_revision_uniq"),
            models.CheckConstraint(condition=models.Q(product_quantity__gt=0), name="fisc_debit_prev_qty_positive"),
            models.CheckConstraint(condition=models.Q(product_unit_price__gt=0), name="fisc_debit_prev_unit_positive"),
            models.CheckConstraint(condition=models.Q(product_total_amount__gt=0), name="fisc_debit_prev_total_positive"),
        ]
        indexes = [
            models.Index(fields=["workshop", "validation_status"], name="fisc_debit_prev_scope_idx"),
            models.Index(fields=["source_access_key", "source_item_sequence"], name="fisc_debit_prev_source_idx"),
        ]
        permissions = [
            ("prepare_nfe_debit_product_preview", "Pode preparar previa de produto de debito"),
            ("approve_nfe_debit_product_preview", "Pode aprovar previa de produto de debito"),
            ("view_nfe_debit_product_preview", "Pode visualizar previa de produto de debito"),
            ("view_nfe_debit_product_preview_payload", "Pode visualizar payload da previa de produto de debito"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.basis_id and self.basis.workshop_id != self.workshop_id:
            raise ValidationError({"basis": "A base pertence a outra oficina."})
        if self.basis_item_id and self.basis_item.basis_id != self.basis_id:
            raise ValidationError({"basis_item": "O item nao pertence a base informada."})
        if self.basis_id and self.basis.status != FiscalReferencedBasisStatus.APPROVED:
            raise ValidationError({"basis": "A previa exige base fiscal aprovada."})
        if self.basis_id and self.basis.fiscal_hypothesis != FiscalHypothesis.DEBIT_FINE_INTEREST:
            raise ValidationError({"basis": "A previa exige hipotese de debito por multa/juros."})
        if self.basis_id and self.basis.external_origin and not self.basis.external_xml_validated:
            raise ValidationError({"basis": "Documento externo exige XML/importacao validada."})
        if self.operation_type != "debit" or self.fiscal_purpose_type != "4":
            raise ValidationError("A previa atual suporta somente debito tipo 4.")
        if self.source_item_sequence != self.basis.source_item_sequence:
            raise ValidationError({"source_item_sequence": "Sequencial divergente da base aprovada."})
        if len(self.source_access_key) != 44 or not self.source_access_key.isdigit():
            raise ValidationError({"source_access_key": "A chave referenciada deve possuir 44 digitos."})
        expected_reference = {"chave": self.source_access_key, "item": self.source_item_sequence}
        if self.dfe_referenciado != expected_reference:
            raise ValidationError({"dfe_referenciado": "O DF-e referenciado deve conter a chave e o item da base aprovada."})
        if len(self.product_cfop) != 4 or not self.product_cfop.isdigit():
            raise ValidationError({"product_cfop": "O CFOP deve possuir 4 digitos."})
        calculated = (self.product_quantity * self.product_unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(calculated - self.product_total_amount) > Decimal("0.01"):
            raise ValidationError({"product_total_amount": "Quantidade x valor unitario diverge do total alem da tolerancia de R$ 0,01."})
        if self.product_total_amount != self.basis_item.credit_debit_base_amount:
            raise ValidationError({"product_total_amount": "O total deve ser exatamente igual a multa + juros da base aprovada."})
        if not self.explicit_value_confirmation:
            raise ValidationError({"explicit_value_confirmation": "Confirme que quantidade, valor unitario, total e CFOP foram definidos explicitamente."})
        required_ibs = ("situacao_tributaria", "classificacao_tributaria")
        missing_ibs = [field for field in required_ibs if not str(self.ibs_cbs_payload.get(field) or "").strip()]
        if missing_ibs:
            raise ValidationError({"ibs_cbs_payload": f"IBS/CBS incompleto: {', '.join(missing_ibs)}."})
        if self.forbidden_tax_groups_detected:
            raise ValidationError({"forbidden_tax_groups_detected": "A previa contem grupos tributarios proibidos."})
        required_product = ("nome", "ncm", "quantidade", "unidade", "subtotal", "total", "codigo_cfop", "dfe_referenciado", "impostos")
        missing_product = [field for field in required_product if self.product_payload.get(field) in (None, "", {})]
        if missing_product:
            raise ValidationError({"product_payload": f"Produto fiscal incompleto: {', '.join(missing_product)}."})
        if self.product_payload.get("dfe_referenciado") != self.dfe_referenciado:
            raise ValidationError({"product_payload": "O produto deve preservar o DF-e referenciado validado."})
        if self.validation_status == FiscalProductPreviewStatus.APPROVED and self.validation_errors:
            raise ValidationError({"validation_errors": "Previa com erros nao pode ser aprovada."})

    def save(self, *args, **kwargs) -> None:
        if self.pk:
            immutable_fields = (
                "workshop_id",
                "basis_id",
                "basis_item_id",
                "revision",
                "operation_type",
                "fiscal_purpose_type",
                "source_access_key",
                "source_item_sequence",
                "dfe_referenciado",
                "product_cfop",
                "product_quantity",
                "product_unit_price",
                "product_total_amount",
                "product_payload",
                "ibs_cbs_payload",
                "preview_payload",
                "forbidden_tax_groups_detected",
                "explicit_value_confirmation",
            )
            persisted = type(self).objects.filter(pk=self.pk).values("validation_status", *immutable_fields).first()
            if persisted and persisted["validation_status"] == FiscalProductPreviewStatus.APPROVED and any(persisted[field] != getattr(self, field) for field in immutable_fields):
                raise ValidationError("Os payloads, referencias e valores de uma previa aprovada sao imutaveis.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"FiscalDebitProductPreview[{self.basis_id}:r{self.revision}]"


class FiscalDocumentEvent(TimeStampedModel):
    document = models.ForeignKey(FiscalDocument, verbose_name="Documento fiscal", on_delete=models.CASCADE, related_name="events")
    related_event = models.ForeignKey("self", verbose_name="Evento relacionado", on_delete=models.PROTECT, null=True, blank=True, related_name="related_cancellations")
    event_type = models.CharField(max_length=20, choices=FiscalDocumentEventType.choices, default=FiscalDocumentEventType.CCE, db_index=True)
    event_sequence = models.PositiveSmallIntegerField()
    event_code = models.CharField(max_length=20, blank=True, default="", db_index=True)
    event_payload_type = models.CharField(max_length=40, blank=True, default="")
    status = models.CharField(max_length=20, choices=FiscalDocumentEventStatus.choices, default=FiscalDocumentEventStatus.STARTED, db_index=True)
    remote_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    remote_event_id = models.CharField(max_length=80, blank=True, default="")
    remote_model = models.CharField(max_length=32, blank=True, default="cce")
    correction_text = models.TextField(blank=True, default="")
    request_payload = models.JSONField(blank=True, default=dict)
    response_payload = models.JSONField(blank=True, default=dict)
    xml_url = models.URLField(blank=True, default="")
    dacce_url = models.URLField(blank=True, default="")
    requested_by = models.ForeignKey("accounts.User", verbose_name="Solicitante", on_delete=models.SET_NULL, null=True, blank=True, related_name="fiscal_document_events")
    legal_confirmation = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["document", "event_type", "event_sequence"], name="unique_fiscal_document_event_sequence"),
            models.UniqueConstraint(fields=["remote_uuid"], condition=~models.Q(remote_uuid=""), name="unique_fiscal_document_event_remote_uuid"),
            models.UniqueConstraint(fields=["related_event", "event_type"], condition=models.Q(related_event__isnull=False, status__in=["started", "sent", "processando", "aprovado", "succeeded", "cancelado", "uncertain"]), name="unique_fiscal_event_active_related_event"),
        ]
        indexes = [
            models.Index(fields=["document", "event_type", "status"]),
            models.Index(fields=["document", "event_type", "event_code", "status"]),
            models.Index(fields=["remote_model", "remote_uuid"]),
            models.Index(fields=["related_event", "event_type", "status"]),
        ]
        permissions = [
            ("issue_nfe_correction", "Pode emitir carta de correcao NF-e"),
            ("download_nfe_correction", "Pode baixar XML/DACCE de carta de correcao NF-e"),
            ("issue_ibs_cbs_event", "Pode registrar evento IBS/CBS"),
            ("cancel_ibs_cbs_event", "Pode cancelar evento IBS/CBS"),
            ("view_ibs_cbs_event", "Pode visualizar evento IBS/CBS"),
            ("download_ibs_cbs_event", "Pode baixar XML de evento IBS/CBS"),
            ("view_ibs_cbs_event_payload", "Pode visualizar payload de evento IBS/CBS"),
        ]

    def __str__(self) -> str:
        return f"FiscalEvent[{self.event_type}:{self.event_sequence}:{self.status}]"


class WebmaniaWebhookEvent(TimeStampedModel):
    model = models.CharField(max_length=32, db_index=True)
    event_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    fingerprint = models.CharField(max_length=64, blank=True, default="", db_index=True)
    payload = models.JSONField(blank=True, default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["fingerprint"], condition=~models.Q(fingerprint=""), name="unique_webmania_webhook_fingerprint"),
        ]
        indexes = [
            models.Index(fields=["model", "event_uuid"]),
            models.Index(fields=["processed_at"]),
        ]

    def __str__(self) -> str:
        return f"Webhook[{self.model}:{self.event_uuid or '-'}]"


class FiscalNumberInutilization(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="fiscal_number_inutilizations")
    account = models.ForeignKey("accounts.Account", verbose_name="Conta", on_delete=models.PROTECT, null=True, blank=True, related_name="fiscal_number_inutilizations")
    document_type = models.CharField(max_length=12, choices=FiscalDocumentType.choices, default=FiscalDocumentType.NFCE, db_index=True)
    environment = models.CharField(max_length=2, db_index=True)
    series = models.CharField(max_length=10, db_index=True)
    sequence_start = models.PositiveIntegerField()
    sequence_end = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=FiscalNumberInutilizationStatus.choices, default=FiscalNumberInutilizationStatus.STARTED, db_index=True)
    remote_status = models.CharField(max_length=64, blank=True, default="")
    request_payload = models.JSONField(blank=True, default=dict)
    response_payload = models.JSONField(blank=True, default=dict)
    remote_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    protocol = models.CharField(max_length=80, blank=True, default="")
    xml_url = models.URLField(blank=True, default="")
    requested_by = models.ForeignKey("accounts.User", verbose_name="Solicitante", on_delete=models.SET_NULL, null=True, blank=True, related_name="fiscal_number_inutilizations")
    requested_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(sequence_start__lte=models.F("sequence_end")), name="valid_fiscal_number_inutilization_range"),
        ]
        indexes = [
            models.Index(fields=["workshop", "document_type", "environment", "series", "status"], name="fiscal_inutil_scope_status_idx"),
            models.Index(fields=["workshop", "document_type", "environment", "series", "sequence_start", "sequence_end"], name="fiscal_inutil_range_idx"),
        ]
        permissions = [
            ("inutilize_nfce_numbering", "Pode inutilizar numeracao NFC-e"),
            ("view_nfce_inutilization", "Pode visualizar inutilizacao NFC-e"),
            ("download_nfce_inutilization", "Pode baixar XML de inutilizacao NFC-e"),
            ("view_nfce_inutilization_payload", "Pode visualizar payload de inutilizacao NFC-e"),
        ]

    def __str__(self) -> str:
        sequence = str(self.sequence_start) if self.sequence_start == self.sequence_end else f"{self.sequence_start}-{self.sequence_end}"
        return f"FiscalNumberInutilization[{self.document_type}:{self.series}:{sequence}:{self.status}]"


class FiscalEmissionAttempt(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="fiscal_emission_attempts")
    document_kind = models.CharField(max_length=12, choices=FiscalEmissionDocumentKind.choices)
    operation_type = models.CharField(max_length=32, choices=FiscalEmissionOperationType.choices, default=FiscalEmissionOperationType.EMISSION, db_index=True)
    request_model = models.CharField(max_length=40)
    request_id = models.PositiveIntegerField()
    fiscal_document = models.ForeignKey(FiscalDocument, verbose_name="Documento fiscal", on_delete=models.SET_NULL, null=True, blank=True, related_name="emission_attempts")
    fiscal_document_event = models.ForeignKey(FiscalDocumentEvent, verbose_name="Evento fiscal", on_delete=models.SET_NULL, null=True, blank=True, related_name="emission_attempts")
    fiscal_number_inutilization = models.ForeignKey(FiscalNumberInutilization, verbose_name="Inutilizacao de numeracao", on_delete=models.SET_NULL, null=True, blank=True, related_name="emission_attempts")
    idempotency_key = models.CharField(max_length=160)
    payload_hash = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=20, choices=FiscalEmissionAttemptStatus.choices, default=FiscalEmissionAttemptStatus.STARTED, db_index=True)
    remote_model = models.CharField(max_length=32, blank=True, default="")
    remote_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    remote_key = models.CharField(max_length=80, blank=True, default="")
    request_payload = models.JSONField(blank=True, default=dict)
    response_payload = models.JSONField(blank=True, default=dict)
    error_message = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "document_kind", "idempotency_key"], name="unique_fiscal_attempt_per_intention"),
        ]
        indexes = [
            models.Index(fields=["workshop", "document_kind", "status"]),
            models.Index(fields=["request_model", "request_id"]),
            models.Index(fields=["operation_type", "status"]),
            models.Index(fields=["fiscal_document_event"]),
            models.Index(fields=["fiscal_number_inutilization"]),
        ]

    def __str__(self) -> str:
        return f"FiscalAttempt[{self.document_kind}:{self.idempotency_key}:{self.status}]"
