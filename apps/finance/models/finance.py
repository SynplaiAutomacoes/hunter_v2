import logging
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.infrastructure.models import TimeStampedModel
from apps.core.workorder_numbers import format_workorder_reference

logger = logging.getLogger(__name__)


DISCOUNT_TYPE_CHOICES: list[tuple[str, str]] = [
    ("products", "Apenas Produtos"),
    ("services", "Apenas Serviços"),
    ("both", "Produtos e Serviços"),
]


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


class NfeFreightMode(models.IntegerChoices):
    SENDER = 0, "Por conta do emitente (CIF)"
    RECIPIENT = 1, "Por conta do destinatario (FOB)"
    THIRD_PARTY = 2, "Por conta de terceiros"
    OWN_SENDER = 3, "Transporte proprio do emitente"
    OWN_RECIPIENT = 4, "Transporte proprio do destinatario"
    NO_TRANSPORT = 9, "Sem transporte"


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
    SUCCEEDED = "succeeded", "Concluída"
    FAILED = "failed", "Falhou"
    UNCERTAIN = "uncertain", "Incerta"


class FiscalEmissionDocumentKind(models.TextChoices):
    NFE = "nfe", "NF-e"


class FiscalEmissionOperationType(models.TextChoices):
    CCE = "cce", "Carta de correção"
    RETURN = "return", "Devolução"
    REVERSAL = "reversal", "Estorno"


class FiscalDocumentType(models.TextChoices):
    NFE = "nfe", "NF-e"


class FiscalDocumentStatus(models.TextChoices):
    PROCESSING = "processando", "Processando"
    APPROVED = "aprovado", "Aprovado"
    REPROVED = "reprovado", "Reprovado"
    CANCELED = "cancelado", "Cancelado"
    DENIED = "denegado", "Denegado"
    CONTINGENCY = "contingencia", "Contingência"
    UNCERTAIN = "uncertain", "Incerto"


class FiscalDocumentOrigin(models.TextChoices):
    LOCAL = "local", "Local"
    EXTERNAL = "external", "Externo"
    DERIVED = "derived", "Derivado"


class FiscalDocumentPurpose(models.TextChoices):
    NORMAL = "normal", "Normal"
    RETURN = "return", "Devolução"
    REVERSAL = "reversal", "Estorno"


class FiscalDocumentComplementaryType(models.TextChoices):
    PRICE_QUANTITY = "price_quantity", "Preço/quantidade"


class FiscalDocumentLinkRole(models.TextChoices):
    RETURNS = "returns", "Devolve"
    REVERSES = "reverses", "Estorna"


class FiscalDocumentEventType(models.TextChoices):
    CCE = "cce", "Carta de correção"


class FiscalDocumentEventStatus(models.TextChoices):
    STARTED = "started", "Iniciado"
    SENT = "sent", "Enviado"
    SUCCEEDED = "succeeded", "Concluído"
    PROCESSING = "processando", "Processando"
    APPROVED = "aprovado", "Aprovado"
    REPROVED = "reprovado", "Reprovado"
    FAILED = "failed", "Falhou"
    UNCERTAIN = "uncertain", "Incerto"


class TaxClassNfe(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="tax_classes_nfe")
    reference = models.CharField(verbose_name="Referência", max_length=30)
    description = models.CharField(verbose_name="Descrição", max_length=255, blank=True, default="")
    status = models.CharField(verbose_name="Status", max_length=30, blank=True, default="")
    remote_date = models.CharField(verbose_name="Data", max_length=40, blank=True, default="")
    remote_updated_date = models.CharField(verbose_name="Data de atualização remota", max_length=40, blank=True, default="")
    informacoes_fisco = models.TextField(verbose_name="Informações ao Fisco", blank=True, default="")
    informacoes_complementares = models.TextField(verbose_name="Informações complementares", blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["workshop", "reference"], name="unique_tax_class_nfe_per_workshop_reference"),
        ]
        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]

    def __str__(self) -> str:
        workshop_id = getattr(self, "workshop_id", "-")
        return f"Nota Fiscal de Produto {self.reference} ({workshop_id})"


class TaxClassNfeIcmsScenario(models.Model):
    tax_class = models.ForeignKey(TaxClassNfe, verbose_name="Classe de Nota Fiscal de Produto", on_delete=models.CASCADE, related_name="icms_scenarios")
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
    tax_class = models.ForeignKey(TaxClassNfe, verbose_name="Classe de Nota Fiscal de Produto", on_delete=models.CASCADE, related_name="ipi_scenarios")
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
    tax_class = models.ForeignKey(TaxClassNfe, verbose_name="Classe de Nota Fiscal de Produto", on_delete=models.CASCADE, related_name="pis_scenarios")
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
    tax_class = models.ForeignKey(TaxClassNfe, verbose_name="Classe de Nota Fiscal de Produto", on_delete=models.CASCADE, related_name="cofins_scenarios")
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
    codigo_nbs = models.CharField(verbose_name="Código NBS", max_length=9, blank=True, default="", help_text="Código NBS da classe NFS-e (Padrão Nacional: 9 dígitos).")
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
    NFE = "nfe", "Nota Fiscal de Produto"
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

    nfe_serie = models.PositiveIntegerField(verbose_name="Série da Nota Fiscal de Produto", null=True, blank=True)
    nfe_numero = models.PositiveIntegerField(verbose_name="Próximo número da Nota Fiscal de Produto", null=True, blank=True)
    nfe_numero_dev = models.PositiveIntegerField(verbose_name="Próximo número da Nota Fiscal de Produto homologação", null=True, blank=True)
    cnae_issqn = models.CharField(verbose_name="CNAE ISSQN", max_length=10, blank=True, default="")

    nfce_serie = models.PositiveIntegerField(verbose_name="Série NFC-e", null=True, blank=True)
    nfce_numero = models.PositiveIntegerField(verbose_name="Próximo número NFC-e", null=True, blank=True)
    nfce_id_csc = models.CharField(verbose_name="ID CSC NFC-e", max_length=60, blank=True, default="")
    nfce_codigo_csc = models.CharField(verbose_name="Código CSC NFC-e", max_length=60, blank=True, default="")
    nfce_numero_dev = models.PositiveIntegerField(verbose_name="Próximo número NFC-e homologação", null=True, blank=True)
    nfce_id_csc_dev = models.CharField(verbose_name="ID CSC NFC-e homologação", max_length=60, blank=True, default="")
    nfce_codigo_csc_dev = models.CharField(verbose_name="Código CSC NFC-e homologação", max_length=60, blank=True, default="")

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
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE, null=True, blank=True)
    recipient_snapshot = models.JSONField(verbose_name="Snapshot do destinatário", blank=True, default=dict)
    recipient_name = models.CharField(verbose_name="Nome do destinatário", max_length=255, blank=True, default="", db_index=True)
    current_step = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=NfseRequestStatus.choices, default=NfseRequestStatus.WAITING_WO)
    pricing_slider = models.SmallIntegerField(
        verbose_name="Slider de precificacao",
        null=True,
        blank=True,
        validators=[MinValueValidator(-100), MaxValueValidator(100)],
        help_text="Copia o slider do orcamento na criacao e permanece independente para a emissao.",
    )
    discount_type_override = models.CharField(
        verbose_name="Tipo de Desconto (Emissao)",
        max_length=10,
        choices=DISCOUNT_TYPE_CHOICES,
        blank=True,
        default="",
        help_text="Sobrescreve o tipo de desconto da OS apenas para esta emissao. Vazio usa o da OS.",
    )
    service_description = models.TextField(verbose_name="Discriminação do Serviço", blank=True, default="")
    additional_information = models.TextField(verbose_name="Informações complementares", blank=True, default="")
    codigo_nbs = models.CharField(
        verbose_name="Código NBS",
        max_length=9,
        blank=True,
        default="",
        help_text="Código NBS da NFS-e (Padrão Nacional: 9 dígitos).",
    )
    tax_class = models.CharField(verbose_name="Classe de Imposto", max_length=30, default="REF000000")
    reserved_rps_number = models.PositiveIntegerField(verbose_name="RPS reservado", null=True, blank=True)
    reserved_rps_series = models.CharField(verbose_name="Série RPS reservada", max_length=20, blank=True, default="")

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
        if self.recipient_name:
            return self.recipient_name
        customer = getattr(getattr(self.workorder, "budget", None), "customer", None)
        if not customer:
            return "-"
        return customer.name

    @property
    def workorder_reference(self) -> str:
        if self.workorder_id is None:
            return "Avulsa"
        return format_workorder_reference(self.workorder)

    @property
    def is_standalone(self) -> bool:
        return self.workorder_id is None

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

        from apps.core.infrastructure.services.webmania.webmania_status import normalize_nfse_request_status

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
        return f"NFS-e Request #{self.pk} - {self.workorder_reference}"

    @property
    def rps_number_display(self) -> str:
        if self.reserved_rps_number is not None:
            return str(self.reserved_rps_number)

        first_item = self.items.order_by("id").first()
        if first_item is None:
            return "-"

        return str(first_item.rps_number or first_item.number or "-")

    @property
    def rps_number_display_listing(self) -> str:
        if self.status == NfseRequestStatus.REPROVED:
            return "-"
        return self.rps_number_display


class NfeRequest(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE, null=True, blank=True)
    recipient_snapshot = models.JSONField(verbose_name="Snapshot do destinatário", blank=True, default=dict)
    recipient_name = models.CharField(verbose_name="Nome do destinatário", max_length=255, blank=True, default="", db_index=True)
    current_step = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=NfeRequestStatus.choices, default=NfeRequestStatus.WAITING_WO)
    pricing_slider = models.SmallIntegerField(
        verbose_name="Slider de precificacao",
        null=True,
        blank=True,
        validators=[MinValueValidator(-100), MaxValueValidator(100)],
        help_text="Copia o slider do orcamento na criacao e permanece independente para a emissao.",
    )
    discount_type_override = models.CharField(
        verbose_name="Tipo de Desconto (Emissao)",
        max_length=10,
        choices=DISCOUNT_TYPE_CHOICES,
        blank=True,
        default="",
        help_text="Sobrescreve o tipo de desconto da OS apenas para esta emissao. Vazio usa o da OS.",
    )
    additional_information = models.TextField(verbose_name="Informações complementares", blank=True, default="")
    tax_class = models.CharField(verbose_name="Classe de Imposto", max_length=30, default="REF000000")
    freight_mode = models.PositiveSmallIntegerField(verbose_name="Modalidade de frete", choices=NfeFreightMode.choices, default=NfeFreightMode.NO_TRANSPORT)
    transport_snapshot = models.JSONField(verbose_name="Snapshot de transporte", blank=True, default=dict)
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
        if self.recipient_name:
            return self.recipient_name
        customer = getattr(getattr(self.workorder, "budget", None), "customer", None)
        if not customer:
            return "-"
        return customer.name

    @property
    def workorder_reference(self) -> str:
        if self.workorder_id is None:
            return "Avulsa"
        return format_workorder_reference(self.workorder)

    @property
    def is_standalone(self) -> bool:
        return self.workorder_id is None

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

        from apps.core.infrastructure.services.webmania.webmania_status import normalize_nfe_request_status

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
        return f"NF-e Request #{self.pk} - {self.workorder_reference}"

    @property
    def number_display(self) -> str:
        if self.reserved_number is not None:
            return str(self.reserved_number)

        first_item = self.items.order_by("id").first()
        if first_item is None:
            return "-"

        return str(first_item.number or "-")

    @property
    def number_display_listing(self) -> str:
        if self.status == NfeRequestStatus.REPROVED:
            return "-"
        return self.number_display


class StandaloneNfeLine(TimeStampedModel):
    nfe_request = models.ForeignKey(NfeRequest, verbose_name="Requisição NF-e", on_delete=models.CASCADE, related_name="standalone_lines")
    product = models.ForeignKey("catalog.Product", verbose_name="Produto", on_delete=models.SET_NULL, null=True, blank=True, related_name="standalone_nfe_lines")
    description = models.CharField(verbose_name="Descrição", max_length=255)
    product_code = models.CharField(verbose_name="Código", max_length=120)
    ncm = models.CharField(verbose_name="NCM", max_length=10)
    cest = models.CharField(verbose_name="CEST", max_length=10, blank=True, default="")
    unit = models.CharField(verbose_name="Unidade", max_length=12, default="UN")
    origin = models.PositiveSmallIntegerField(verbose_name="Origem tributária", default=0)
    quantity = models.DecimalField(verbose_name="Quantidade", max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0.0001"))])
    unit_value = models.DecimalField(verbose_name="Valor unitário", max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0"))])
    sort_order = models.PositiveIntegerField(verbose_name="Ordem", default=0)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Linha avulsa de NF-e"
        verbose_name_plural = "Linhas avulsas de NF-e"
        ordering = ("sort_order", "id")

    @property
    def total_value(self) -> Decimal:
        return self.quantity * self.unit_value

    def __str__(self) -> str:
        return f"{self.description} x {self.quantity}"


class StandaloneNfseLine(TimeStampedModel):
    nfse_request = models.ForeignKey(NfseRequest, verbose_name="Requisição NFS-e", on_delete=models.CASCADE, related_name="standalone_lines")
    service = models.ForeignKey("catalog.Service", verbose_name="Serviço", on_delete=models.SET_NULL, null=True, blank=True, related_name="standalone_nfse_lines")
    description = models.CharField(verbose_name="Descrição", max_length=255)
    quantity = models.DecimalField(verbose_name="Quantidade", max_digits=15, decimal_places=4, default=Decimal("1"), validators=[MinValueValidator(Decimal("0.0001"))])
    unit_value = models.DecimalField(verbose_name="Valor unitário", max_digits=15, decimal_places=4, validators=[MinValueValidator(Decimal("0"))])
    sort_order = models.PositiveIntegerField(verbose_name="Ordem", default=0)

    class Meta(TimeStampedModel.Meta):
        verbose_name = "Linha avulsa de NFS-e"
        verbose_name_plural = "Linhas avulsas de NFS-e"
        ordering = ("sort_order", "id")

    @property
    def total_value(self) -> Decimal:
        return self.quantity * self.unit_value

    def __str__(self) -> str:
        return f"{self.description} x {self.quantity}"


class NfseBatch(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE, null=True, blank=True)
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
    last_sync_error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="unique_nfse_batch_uuid"),
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
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="unique_nfse_item_uuid"),
        ]

        indexes = [
            models.Index(fields=["workshop", "status"]),
        ]


class NfeItem(models.Model):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE)
    workorder = models.ForeignKey("workorder.WorkOrder", verbose_name="Ordem de Serviço", on_delete=models.CASCADE, null=True, blank=True)
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
            models.UniqueConstraint(fields=["uuid"], name="unique_nfe_item_uuid"),
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
    legacy_nfe_item = models.OneToOneField(NfeItem, verbose_name="Item legado NF-e", on_delete=models.CASCADE, null=True, blank=True, related_name="fiscal_document")
    remote_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    access_key = models.CharField(max_length=80, blank=True, default="", db_index=True)
    series = models.CharField(max_length=20, blank=True, default="")
    number = models.CharField(max_length=40, blank=True, default="")
    receipt = models.CharField(max_length=40, blank=True, default="")
    environment = models.CharField(max_length=10, blank=True, default="")
    status = models.CharField(max_length=20, choices=FiscalDocumentStatus.choices, default=FiscalDocumentStatus.APPROVED, db_index=True)
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
        ]
        indexes = [
            models.Index(fields=["workshop", "document_type", "status"]),
            models.Index(fields=["workshop", "document_type", "origin", "purpose"]),
        ]
        permissions = [
            ("issue_nfe_return", "Pode emitir NF-e de devolução"),
            ("issue_nfe_reversal", "Pode emitir NF-e de estorno"),
            ("download_nfe_return", "Pode baixar XML/DANFE de NF-e de devolução ou estorno"),
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


class FiscalDocumentEvent(TimeStampedModel):
    document = models.ForeignKey(FiscalDocument, verbose_name="Documento fiscal", on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=FiscalDocumentEventType.choices, default=FiscalDocumentEventType.CCE, db_index=True)
    event_sequence = models.PositiveSmallIntegerField()
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
        ]
        indexes = [
            models.Index(fields=["document", "event_type", "status"]),
            models.Index(fields=["remote_model", "remote_uuid"]),
        ]
        permissions = [
            ("issue_nfe_correction", "Pode emitir carta de correção NF-e"),
            ("download_nfe_correction", "Pode baixar XML/DACCE de carta de correção NF-e"),
        ]

    def __str__(self) -> str:
        return f"FiscalEvent[{self.event_type}:{self.event_sequence}:{self.status}]"


class FiscalEmissionAttempt(TimeStampedModel):
    workshop = models.ForeignKey("workshops.Workshop", verbose_name="Oficina", on_delete=models.CASCADE, related_name="fiscal_emission_attempts")
    document_kind = models.CharField(max_length=12, choices=FiscalEmissionDocumentKind.choices, default=FiscalEmissionDocumentKind.NFE)
    operation_type = models.CharField(max_length=32, choices=FiscalEmissionOperationType.choices, default=FiscalEmissionOperationType.CCE, db_index=True)
    request_model = models.CharField(max_length=40)
    request_id = models.PositiveIntegerField()
    fiscal_document = models.ForeignKey(FiscalDocument, verbose_name="Documento fiscal", on_delete=models.SET_NULL, null=True, blank=True, related_name="emission_attempts")
    fiscal_document_event = models.ForeignKey(FiscalDocumentEvent, verbose_name="Evento fiscal", on_delete=models.SET_NULL, null=True, blank=True, related_name="emission_attempts")
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
            models.Index(fields=["operation_type", "status"]),
            models.Index(fields=["fiscal_document_event"]),
        ]

    def __str__(self) -> str:
        return f"FiscalAttempt[{self.document_kind}:{self.idempotency_key}:{self.status}]"


class WebmaniaWebhookEvent(TimeStampedModel):
    model = models.CharField(max_length=32, db_index=True)
    event_uuid = models.CharField(max_length=64, blank=True, default="", db_index=True)
    payload = models.JSONField(blank=True, default=dict)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True, default="")

    class Meta(TimeStampedModel.Meta):
        indexes = [
            models.Index(fields=["model", "event_uuid"]),
            models.Index(fields=["processed_at"]),
        ]

    def __str__(self) -> str:
        return f"Webhook[{self.model}:{self.event_uuid or '-'}]"
