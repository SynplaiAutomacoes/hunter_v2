from __future__ import annotations

from decimal import Decimal
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django import forms
from django.urls import reverse

from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.presentation.widgets import CEPInput, CPForCNPJInput, CheckboxInput, EmailInput, PasswordInput, PhoneInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.models.finance import WebmaniaCompany, WebmaniaCompanyTaxType
from apps.core.infrastructure.services.webmania.webmania_secrets import encrypt_secret
from apps.core.text_normalization import name_case, sentence_case
from apps.core.presentation.forms import CoreModelForm


WEBMANIA_REGIME_TRIBUTARIO_CHOICES = [
    ("", "Selecione"),
    ("lucro_real", "Lucro Real"),
    ("lucro_presumido", "Lucro Presumido"),
]

WEBMANIA_UNIDADE_EMPRESA_CHOICES = [
    ("", "Selecione"),
    ("matriz", "Matriz"),
    ("filial", "Filial"),
]

WEBMANIA_ORIENTACAO_DANFE_CHOICES = [
    ("", "Selecione"),
    ("P", "Retrato"),
    ("L", "Paisagem"),
]

WEBMANIA_ENABLED_FLAG_CHOICES = [
    ("", "Selecione"),
    ("1", "Sim"),
    ("0", "Não"),
]

WEBMANIA_HOMOLOG_ONLY_FIELDS = (
    "nfe_numero_dev",
    "nfce_numero_dev",
    "nfce_id_csc_dev",
    "nfce_codigo_csc_dev",
    "nfse_rps_numero_dev",
)


def _format_decimal(value: Decimal, *, places: int = 2) -> str:
    quantizer = Decimal(1).scaleb(-places)
    return f"{value.quantize(quantizer):f}"


def digits_only(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_webmania_phone_widget_value(value: object) -> str:
    """Match PhoneInput hidden value (+55 + local digits) to avoid false changed_data."""
    digits = digits_only(value)
    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]
    if not digits:
        return ""
    if len(digits) > 11:
        return str(value or "").strip()
    return f"+55{digits}"


def normalize_telefone_for_webmania_api(value: object) -> str:
    digits = digits_only(value)
    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]
    return digits


def apply_webmania_widget_initials(form: forms.BaseForm, *, instance: WebmaniaCompany) -> None:
    """Align form.initial with Alpine widget normalization so untouched fields stay out of changed_data."""
    if "cnpj" in form.fields:
        form.initial["cnpj"] = digits_only(getattr(instance, "cnpj", ""))
    if "cpf" in form.fields:
        form.initial["cpf"] = digits_only(getattr(instance, "cpf", ""))[:11]
    if "cep" in form.fields:
        form.initial["cep"] = digits_only(getattr(instance, "cep", ""))[:8]
    if "telefone" in form.fields:
        form.initial["telefone"] = normalize_webmania_phone_widget_value(getattr(instance, "telefone", ""))


def apply_person_company_document_exclusivity(cleaned_data: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
    """
    PJ and PF fields are mutually exclusive for Webmania.
    Returns (cleaned_data, clear_person_fields, clear_company_fields).
    """
    cnpj = digits_only(cleaned_data.get("cnpj"))
    cpf = digits_only(cleaned_data.get("cpf"))[:11]
    razao_social = str(cleaned_data.get("razao_social") or "").strip()
    nome_completo = str(cleaned_data.get("nome_completo") or "").strip()

    cleaned_data["cnpj"] = cnpj
    cleaned_data["cpf"] = cpf

    has_pj_data = bool(cnpj or razao_social)
    has_pf_data = bool(cpf or nome_completo)

    if has_pj_data:
        cleaned_data["cpf"] = ""
        cleaned_data["nome_completo"] = ""
        return cleaned_data, True, False

    if has_pf_data:
        cleaned_data["cnpj"] = ""
        cleaned_data["razao_social"] = ""
        return cleaned_data, False, True

    return cleaned_data, False, False


def finalize_webmania_company_api_payload(
    payload: dict[str, Any],
    *,
    initial_values: dict[str, Any],
    clear_person_fields: bool = False,
    clear_company_fields: bool = False,
) -> dict[str, Any]:
    """Normalize document/address contact fields and clear the opposite person type when needed."""
    for field_name in ("cnpj", "cpf", "cep"):
        if field_name in payload:
            max_len = 11 if field_name == "cpf" else 14 if field_name == "cnpj" else 8
            payload[field_name] = digits_only(payload[field_name])[:max_len]

    if "telefone" in payload:
        payload["telefone"] = normalize_telefone_for_webmania_api(payload["telefone"])

    if clear_person_fields:
        had_pf = bool(str(initial_values.get("cpf") or "").strip() or str(initial_values.get("nome_completo") or "").strip())
        if had_pf or "cnpj" in payload or "razao_social" in payload:
            payload["cpf"] = ""
            payload["nome_completo"] = ""

    if clear_company_fields:
        had_pj = bool(str(initial_values.get("cnpj") or "").strip() or str(initial_values.get("razao_social") or "").strip())
        if had_pj or "cpf" in payload or "nome_completo" in payload:
            payload["cnpj"] = ""
            payload["razao_social"] = ""

    return payload


class WebmaniaCompanyUpdateForm(CoreModelForm):
    secret_fields = ("nfse_password", "nfse_token", "certificado", "certificado_senha")
    nullable_boolean_fields = (
        "partilha_icms_contribuinte",
        "partilha_icms_isento",
        "microcervejaria",
        "icms_ref_sp",
        "refeicoes_sp",
        "icms_ref_df",
        "exclusao_icms_pis_cofins",
        "exclusao_difal_pis_cofins",
        "deduzir_desconto_ipi",
        "email_automatico_nfse",
    )

    tipo_tributacao = forms.ChoiceField(required=False, choices=[("", "Selecione"), *WebmaniaCompanyTaxType.choices], widget=SearchableSelectInput(choices=[("", "Selecione"), *WebmaniaCompanyTaxType.choices]))
    regime_tributario = forms.ChoiceField(required=False, choices=WEBMANIA_REGIME_TRIBUTARIO_CHOICES, widget=SearchableSelectInput(choices=WEBMANIA_REGIME_TRIBUTARIO_CHOICES))
    unidade_empresa = forms.ChoiceField(required=False, choices=WEBMANIA_UNIDADE_EMPRESA_CHOICES, widget=SearchableSelectInput(choices=WEBMANIA_UNIDADE_EMPRESA_CHOICES))
    orientacao_danfe = forms.ChoiceField(required=False, choices=WEBMANIA_ORIENTACAO_DANFE_CHOICES, widget=SearchableSelectInput(choices=WEBMANIA_ORIENTACAO_DANFE_CHOICES))
    desativar_epec = forms.ChoiceField(required=False, choices=WEBMANIA_ENABLED_FLAG_CHOICES, widget=SearchableSelectInput(choices=WEBMANIA_ENABLED_FLAG_CHOICES))
    ocultar_total_etiqueta = forms.ChoiceField(required=False, choices=WEBMANIA_ENABLED_FLAG_CHOICES, widget=SearchableSelectInput(choices=WEBMANIA_ENABLED_FLAG_CHOICES))

    class Meta:
        model = WebmaniaCompany
        fields = [
            "tipo_tributacao",
            "regime_tributario",
            "cnpj",
            "razao_social",
            "cpf",
            "nome_completo",
            "nome_fantasia",
            "ie",
            "im",
            "unidade_empresa",
            "email",
            "telefone",
            "conta_bancaria_banco",
            "conta_bancaria_agencia",
            "conta_bancaria_numero",
            "conta_bancaria_digito",
            "contabilidade",
            "url_notificacao",
            "logomarca",
            "cep",
            "endereco",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
            "nfe_serie",
            "nfe_numero",
            "nfe_numero_dev",
            "cnae_issqn",
            "nfce_serie",
            "nfce_numero",
            "nfce_id_csc",
            "nfce_codigo_csc",
            "nfce_numero_dev",
            "nfce_id_csc_dev",
            "nfce_codigo_csc_dev",
            "informacoes_fisco",
            "nfse_rps_serie",
            "nfse_rps_numero",
            "cnae",
            "nfse_login",
            "nfse_password",
            "nfse_token",
            "regime_apuracao_sn",
            "regime_especial_nacional",
            "regime_especial_municipal",
            "nfse_lote_rps_numero",
            "nfse_rps_numero_dev",
            "certificado",
            "certificado_senha",
            "partilha_icms_contribuinte",
            "partilha_icms_isento",
            "orientacao_danfe",
            "microcervejaria",
            "icms_ref_sp",
            "refeicoes_sp",
            "icms_ref_df",
            "exclusao_icms_pis_cofins",
            "exclusao_difal_pis_cofins",
            "deduzir_desconto_ipi",
            "email_automatico_nfse",
            "desativar_epec",
            "ocultar_total_etiqueta",
        ]
        widgets = {
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "cpf": CPForCNPJInput(mode="cpf"),
            "email": EmailInput(),
            "telefone": PhoneInput(),
            "cep": CEPInput(),
            "razao_social": TextInput(),
            "nome_completo": TextInput(),
            "nome_fantasia": TextInput(),
            "ie": TextInput(),
            "im": TextInput(),
            "conta_bancaria_banco": TextInput(),
            "conta_bancaria_agencia": TextInput(),
            "conta_bancaria_numero": TextInput(),
            "conta_bancaria_digito": TextInput(),
            "contabilidade": TextInput(),
            "url_notificacao": TextInput(),
            "logomarca": TextInput(),
            "endereco": TextInput(),
            "numero": TextInput(),
            "complemento": TextInput(),
            "bairro": TextInput(),
            "cidade": TextInput(),
            "uf": TextInput(),
            "cnae_issqn": TextInput(),
            "nfce_id_csc": TextInput(),
            "nfce_codigo_csc": TextInput(),
            "nfce_id_csc_dev": TextInput(),
            "nfce_codigo_csc_dev": TextInput(),
            "informacoes_fisco": TextareaInput(rows=3),
            "nfse_rps_serie": TextInput(),
            "cnae": TextInput(),
            "nfse_login": TextInput(),
            "nfse_password": PasswordInput(),
            "nfse_token": PasswordInput(),
            "regime_apuracao_sn": TextInput(),
            "regime_especial_nacional": TextInput(),
            "regime_especial_municipal": TextInput(),
            "certificado": TextareaInput(rows=4),
            "certificado_senha": PasswordInput(),
            "partilha_icms_contribuinte": CheckboxInput(),
            "partilha_icms_isento": CheckboxInput(),
            "microcervejaria": CheckboxInput(),
            "icms_ref_sp": CheckboxInput(),
            "refeicoes_sp": CheckboxInput(),
            "icms_ref_df": CheckboxInput(),
            "exclusao_icms_pis_cofins": CheckboxInput(),
            "exclusao_difal_pis_cofins": CheckboxInput(),
            "deduzir_desconto_ipi": CheckboxInput(),
            "email_automatico_nfse": CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._clear_person_type_fields = False
        self._clear_company_type_fields = False

        self.show_homolog_fields = get_fiscal_service().is_homolog_environment()
        if not self.show_homolog_fields:
            for field_name in WEBMANIA_HOMOLOG_ONLY_FIELDS:
                self.fields.pop(field_name, None)

        self._initial_model_values = {field_name: getattr(self.instance, field_name, "") for field_name in self.Meta.fields}
        self._initial_secret_values = {field_name: getattr(self.instance, field_name, "") for field_name in self.secret_fields}
        apply_webmania_widget_initials(self, instance=self.instance)

        self.fields["email"].required = True

        certificate_management_help = "O certificado A1 e gerenciado exclusivamente na configuracao da oficina."
        for field_name in ("certificado", "certificado_senha"):
            if field_name in self.fields:
                self.fields[field_name].disabled = True
                self.fields[field_name].help_text = certificate_management_help

        if "logomarca" in self.fields:
            self.fields["logomarca"].disabled = True
            self.fields["logomarca"].help_text = "A URL da logomarca e sincronizada automaticamente com o upload da logo da oficina."

        for field_name in self.secret_fields:
            if field_name in self.fields:
                self.initial[field_name] = ""

        for field_name in self.nullable_boolean_fields:
            if getattr(self.instance, field_name, None) is None:
                self.initial[field_name] = False

        cancel_url = reverse("finance:webmania_company_detail", kwargs={"pk": self.instance.pk})

        nfe_fields: list[Any] = [
            HTML("<p class='col-span-12 text-sm font-semibold text-base-content/80'>NF-e</p>"),
            Field("nfe_serie", wrapper_class="col-span-12 lg:col-span-3"),
            Field("nfe_numero", wrapper_class="col-span-12 lg:col-span-3"),
        ]
        if self.show_homolog_fields:
            nfe_fields.append(Field("nfe_numero_dev", wrapper_class="col-span-12 lg:col-span-3"))

        nfce_fields: list[Any] = [
            HTML("<div class='col-span-12 divider my-1'></div>"),
            HTML("<p class='col-span-12 text-sm font-semibold text-base-content/80'>NFC-e</p>"),
            Field("nfce_serie", wrapper_class="col-span-12 lg:col-span-3"),
            Field("nfce_numero", wrapper_class="col-span-12 lg:col-span-3"),
        ]
        if self.show_homolog_fields:
            nfce_fields.extend(
                [
                    Field("nfce_numero_dev", wrapper_class="col-span-12 lg:col-span-3"),
                ]
            )
        nfce_fields.extend(
            [
                Field("nfce_id_csc", wrapper_class="col-span-12 lg:col-span-6"),
                Field("nfce_codigo_csc", wrapper_class="col-span-12 lg:col-span-6"),
            ]
        )
        if self.show_homolog_fields:
            nfce_fields.extend(
                [
                    Field("nfce_id_csc_dev", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("nfce_codigo_csc_dev", wrapper_class="col-span-12 lg:col-span-6"),
                ]
            )

        nfse_fields: list[Any] = [
            HTML("<div class='col-span-12 divider my-1'></div>"),
            HTML("<p class='col-span-12 text-sm font-semibold text-base-content/80'>NFS-e</p>"),
            Field("nfse_rps_serie", wrapper_class="col-span-12 lg:col-span-3"),
            Field("nfse_rps_numero", wrapper_class="col-span-12 lg:col-span-3"),
            Field("nfse_lote_rps_numero", wrapper_class="col-span-12 lg:col-span-3"),
        ]
        if self.show_homolog_fields:
            nfse_fields.append(Field("nfse_rps_numero_dev", wrapper_class="col-span-12 lg:col-span-3"))
        nfse_fields.extend(
            [
                Field("cnae", wrapper_class="col-span-12 lg:col-span-3"),
                Field("regime_apuracao_sn", wrapper_class="col-span-12 lg:col-span-3"),
                Field("regime_especial_nacional", wrapper_class="col-span-12 lg:col-span-3"),
                Field("regime_especial_municipal", wrapper_class="col-span-12 lg:col-span-3"),
            ]
        )

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Div(
                HTML("<h3 class='col-span-12 text-xl font-bold'>Dados principais</h3>"),
                Field("tipo_tributacao", wrapper_class="col-span-12 lg:col-span-3"),
                Field("regime_tributario", wrapper_class="col-span-12 lg:col-span-3"),
                Field("unidade_empresa", wrapper_class="col-span-12 lg:col-span-3"),
                Field("ie", wrapper_class="col-span-12 lg:col-span-3"),
                Field("cnpj", wrapper_class="col-span-12 lg:col-span-4"),
                Field("razao_social", wrapper_class="col-span-12 lg:col-span-8"),
                Field("cpf", wrapper_class="col-span-12 lg:col-span-4"),
                Field("nome_completo", wrapper_class="col-span-12 lg:col-span-8"),
                Field("nome_fantasia", wrapper_class="col-span-12 lg:col-span-6"),
                Field("email", wrapper_class="col-span-12 lg:col-span-3"),
                Field("telefone", wrapper_class="col-span-12 lg:col-span-3"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
            HTML("<div class='divider'></div>"),
            Div(
                HTML("<h3 class='col-span-12 text-xl font-bold'>Endereço e contato</h3>"),
                Field("cep", wrapper_class="col-span-12 lg:col-span-3"),
                Field("endereco", wrapper_class="col-span-12 lg:col-span-5"),
                Field("numero", wrapper_class="col-span-12 lg:col-span-2"),
                Field("complemento", wrapper_class="col-span-12 lg:col-span-2"),
                Field("bairro", wrapper_class="col-span-12 lg:col-span-4"),
                Field("cidade", wrapper_class="col-span-12 lg:col-span-4"),
                Field("uf", wrapper_class="col-span-12 lg:col-span-1"),
                Field("contabilidade", wrapper_class="col-span-12 lg:col-span-3"),
                Field("url_notificacao", wrapper_class="col-span-12 lg:col-span-6"),
                Field("logomarca", wrapper_class="col-span-12 lg:col-span-6"),
                Field("conta_bancaria_banco", wrapper_class="col-span-12 lg:col-span-2"),
                Field("conta_bancaria_agencia", wrapper_class="col-span-12 lg:col-span-3"),
                Field("conta_bancaria_numero", wrapper_class="col-span-12 lg:col-span-4"),
                Field("conta_bancaria_digito", wrapper_class="col-span-12 lg:col-span-1"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
            HTML("<div class='divider'></div>"),
            Div(
                HTML("<h3 class='col-span-12 text-xl font-bold'>Configuração fiscal</h3>"),
                HTML("<p class='col-span-12 text-sm font-semibold text-base-content/80'>Geral</p>"),
                Field("informacoes_fisco", wrapper_class="col-span-12"),
                Field("cnae_issqn", wrapper_class="col-span-12 lg:col-span-3"),
                HTML("<div class='col-span-12 divider my-1'></div>"),
                *nfe_fields,
                *nfce_fields,
                *nfse_fields,
                HTML("<div class='col-span-12 divider my-1'></div>"),
                HTML("<p class='col-span-12 text-sm font-semibold text-base-content/80'>Acesso NFS-e e certificado</p>"),
                Field("nfse_login", wrapper_class="col-span-12 lg:col-span-4"),
                Field("nfse_password", wrapper_class="col-span-12 lg:col-span-4"),
                Field("nfse_token", wrapper_class="col-span-12 lg:col-span-4"),
                Field("certificado", wrapper_class="col-span-12 lg:col-span-8"),
                Field("certificado_senha", wrapper_class="col-span-12 lg:col-span-4"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
            HTML("<div class='divider'></div>"),
            Div(
                HTML("<h3 class='col-span-12 text-xl font-bold'>Opcionais</h3>"),
                Field("partilha_icms_contribuinte", wrapper_class="col-span-12 lg:col-span-4"),
                Field("partilha_icms_isento", wrapper_class="col-span-12 lg:col-span-4"),
                Field("microcervejaria", wrapper_class="col-span-12 lg:col-span-4"),
                Field("icms_ref_sp", wrapper_class="col-span-12 lg:col-span-4"),
                Field("refeicoes_sp", wrapper_class="col-span-12 lg:col-span-4"),
                Field("icms_ref_df", wrapper_class="col-span-12 lg:col-span-4"),
                Field("exclusao_icms_pis_cofins", wrapper_class="col-span-12 lg:col-span-4"),
                Field("exclusao_difal_pis_cofins", wrapper_class="col-span-12 lg:col-span-4"),
                Field("deduzir_desconto_ipi", wrapper_class="col-span-12 lg:col-span-4"),
                Field("email_automatico_nfse", wrapper_class="col-span-12 lg:col-span-4"),
                Field("orientacao_danfe", wrapper_class="col-span-12 lg:col-span-4"),
                Field("desativar_epec", wrapper_class="col-span-12 lg:col-span-4"),
                Field("ocultar_total_etiqueta", wrapper_class="col-span-12 lg:col-span-4"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
            HTML("<div class='divider'></div>"),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar alterações", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean(self) -> dict[str, Any]:
        cleaned_data_raw = super().clean()
        cleaned_data: dict[str, Any] = dict(cleaned_data_raw or {})

        if "cep" in cleaned_data:
            cleaned_data["cep"] = digits_only(cleaned_data.get("cep"))[:8]
        if "telefone" in cleaned_data:
            cleaned_data["telefone"] = normalize_webmania_phone_widget_value(cleaned_data.get("telefone"))

        cnpj = digits_only(cleaned_data.get("cnpj"))
        cpf = digits_only(cleaned_data.get("cpf"))[:11]
        razao_social = str(cleaned_data.get("razao_social") or "").strip()
        nome_completo = str(cleaned_data.get("nome_completo") or "").strip()

        has_pj_data = bool(cnpj or razao_social)
        has_pf_data = bool(cpf or nome_completo)

        if not has_pj_data and not has_pf_data:
            message = "Preencha CNPJ + Razão Social ou CPF + Nome Completo."
            self.add_error("cnpj", message)
            self.add_error("cpf", message)
            self.add_error("razao_social", message)
            self.add_error("nome_completo", message)
            return cleaned_data

        cleaned_data, self._clear_person_type_fields, self._clear_company_type_fields = apply_person_company_document_exclusivity(cleaned_data)

        if self._clear_person_type_fields:
            if not digits_only(cleaned_data.get("cnpj")):
                self.add_error("cnpj", "Ao informar Razão Social, o CNPJ é obrigatório.")
            if not str(cleaned_data.get("razao_social") or "").strip():
                self.add_error("razao_social", "Ao informar CNPJ, a Razão Social é obrigatória.")
            return cleaned_data

        if not digits_only(cleaned_data.get("cpf")):
            self.add_error("cpf", "Ao informar Nome Completo, o CPF é obrigatório.")
        if not str(cleaned_data.get("nome_completo") or "").strip():
            self.add_error("nome_completo", "Ao informar CPF, o Nome Completo é obrigatório.")

        return cleaned_data

    def clean_razao_social(self) -> str:
        value = self.cleaned_data.get("razao_social")
        return name_case(value) if value else value

    def clean_nome_completo(self) -> str:
        value = self.cleaned_data.get("nome_completo")
        return name_case(value) if value else value

    def clean_nome_fantasia(self) -> str:
        value = self.cleaned_data.get("nome_fantasia")
        return name_case(value) if value else value

    def clean_conta_bancaria_banco(self) -> str:
        value = self.cleaned_data.get("conta_bancaria_banco")
        return sentence_case(value) if value else value

    def clean_contabilidade(self) -> str:
        value = self.cleaned_data.get("contabilidade")
        return sentence_case(value) if value else value

    def clean_endereco(self) -> str:
        value = self.cleaned_data.get("endereco")
        return sentence_case(value) if value else value

    def clean_complemento(self) -> str:
        value = self.cleaned_data.get("complemento")
        return sentence_case(value) if value else value

    def clean_bairro(self) -> str:
        value = self.cleaned_data.get("bairro")
        return sentence_case(value) if value else value

    def clean_cidade(self) -> str:
        value = self.cleaned_data.get("cidade")
        return sentence_case(value) if value else value

    def clean_informacoes_fisco(self) -> str:
        value = self.cleaned_data.get("informacoes_fisco")
        return sentence_case(value) if value else value

    def build_api_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field_name in self.Meta.fields:
            if field_name not in self.changed_data:
                continue

            value = self.cleaned_data.get(field_name)

            if field_name in self.secret_fields:
                secret_value = str(value or "").strip()
                if secret_value:
                    payload[field_name] = secret_value
                continue

            if isinstance(value, bool):
                payload[field_name] = value
                continue

            if isinstance(value, Decimal):
                payload[field_name] = _format_decimal(value, places=2)
                continue

            if value is None:
                payload[field_name] = ""
                continue

            if isinstance(value, int):
                payload[field_name] = value
                continue

            payload[field_name] = str(value).strip()

        return finalize_webmania_company_api_payload(
            payload,
            initial_values=dict(getattr(self, "_initial_model_values", {})),
            clear_person_fields=bool(getattr(self, "_clear_person_type_fields", False)),
            clear_company_fields=bool(getattr(self, "_clear_company_type_fields", False)),
        )

    def save(self, commit: bool = True) -> WebmaniaCompany:
        original_values = dict(getattr(self, "_initial_model_values", {}))
        existing_secret_values = dict(getattr(self, "_initial_secret_values", {}))
        instance: WebmaniaCompany = super().save(commit=False)

        for field_name in self.Meta.fields:
            if field_name not in self.changed_data:
                setattr(instance, field_name, original_values.get(field_name))

        for field_name in self.secret_fields:
            raw_value = str(self.cleaned_data.get(field_name) or "").strip()
            if raw_value:
                setattr(instance, field_name, encrypt_secret(raw_value))
                continue

            setattr(instance, field_name, existing_secret_values.get(field_name, ""))

        if getattr(self, "_clear_person_type_fields", False):
            instance.cpf = ""
            instance.nome_completo = ""
        elif getattr(self, "_clear_company_type_fields", False):
            instance.cnpj = ""
            instance.razao_social = ""

        if commit:
            instance.save()

        return instance
