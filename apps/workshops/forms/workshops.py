from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.presentation.forms import CoreForm, CoreModelForm
from apps.core.infrastructure.services.webmania.webmania import is_webmania_homolog_environment
from apps.core.presentation.widgets import (
    CEPInput,
    CheckboxInput,
    CPForCNPJInput,
    EmailInput,
    ImageInput,
    NumberInput,
    PhoneInput,
    SearchableSelectInput,
    TextInput,
    TextareaInput,
    PasswordInput,
)
from apps.finance.forms.webmania import (
    WEBMANIA_HOMOLOG_ONLY_FIELDS,
    WEBMANIA_ENABLED_FLAG_CHOICES,
    WEBMANIA_ORIENTACAO_DANFE_CHOICES,
    WEBMANIA_REGIME_TRIBUTARIO_CHOICES,
    WEBMANIA_UNIDADE_EMPRESA_CHOICES,
)
from apps.finance.models.finance import WebmaniaCompany, WebmaniaCompanyTaxType
from apps.core.infrastructure.services.webmania.webmania_secrets import encrypt_secret
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def _format_decimal(value: Decimal, *, places: int = 2) -> str:
    quantizer = Decimal(1).scaleb(-places)
    return f"{value.quantize(quantizer):f}"


class WorkshopForm(CoreModelForm):
    class Meta:
        model = Workshop
        fields = ["name", "cnpj", "phone", "address", "uf", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Oficina Hunter"}),
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "phone": PhoneInput(),
            "address": TextInput(attrs={"placeholder": "Rua das Oficinas, 123"}),
            "uf": TextInput(attrs={"placeholder": "SP"}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk and not self.data:
            self.initial["uf"] = ""

        cancel_url = reverse("workshops:list")

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12 lg:col-span-6"),
                Field("cnpj", wrapper_class="col-span-12 lg:col-span-6"),
                Field("phone", wrapper_class="col-span-12 lg:col-span-6"),
                Field("address", wrapper_class="col-span-12 lg:col-span-6"),
                Field("uf", wrapper_class="col-span-12 lg:col-span-6"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-6"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )


class _PreviewableFileValue:
    def __init__(self, url: str) -> None:
        self.url = url


class BaseWebmaniaCompanySectionForm(CoreModelForm):
    secret_fields: tuple[str, ...] = ()
    nullable_boolean_fields: tuple[str, ...] = ()

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        self.workshop = workshop
        super().__init__(*args, **kwargs)
        self.show_homolog_fields = is_webmania_homolog_environment()
        if not self.show_homolog_fields:
            for field_name in WEBMANIA_HOMOLOG_ONLY_FIELDS:
                self.fields.pop(field_name, None)

        field_names = tuple(getattr(self.Meta, "fields", ()))
        self._initial_model_values = {field_name: getattr(self.instance, field_name, "") for field_name in field_names}
        self._initial_secret_values = {field_name: getattr(self.instance, field_name, "") for field_name in self.secret_fields}

        for field_name in self.secret_fields:
            if field_name in self.fields:
                self.initial[field_name] = ""

        for field_name in self.nullable_boolean_fields:
            if field_name in self.fields and getattr(self.instance, field_name, None) is None:
                self.initial[field_name] = False

    def build_api_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}

        for field_name in getattr(self.Meta, "fields", ()):  # type: ignore[attr-defined]
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

        return payload

    def save(self, commit: bool = True) -> WebmaniaCompany:
        original_values = dict(getattr(self, "_initial_model_values", {}))
        existing_secret_values = dict(getattr(self, "_initial_secret_values", {}))
        instance: WebmaniaCompany = super().save(commit=False)

        for field_name in getattr(self.Meta, "fields", ()):  # type: ignore[attr-defined]
            if field_name not in self.changed_data:
                setattr(instance, field_name, original_values.get(field_name))

        for field_name in self.secret_fields:
            if field_name not in self.fields:
                continue

            raw_value = str(self.cleaned_data.get(field_name) or "").strip()
            if raw_value:
                setattr(instance, field_name, encrypt_secret(raw_value))
                continue

            setattr(instance, field_name, existing_secret_values.get(field_name, ""))

        if commit:
            instance.save()

        return instance


class WorkshopCompanySectionForm(BaseWebmaniaCompanySectionForm):
    tipo_tributacao = forms.ChoiceField(
        required=False,
        choices=[("", "Selecione"), *WebmaniaCompanyTaxType.choices],
        widget=SearchableSelectInput(choices=[("", "Selecione"), *WebmaniaCompanyTaxType.choices]),
    )
    regime_tributario = forms.ChoiceField(
        required=False,
        choices=WEBMANIA_REGIME_TRIBUTARIO_CHOICES,
        widget=SearchableSelectInput(choices=WEBMANIA_REGIME_TRIBUTARIO_CHOICES),
    )
    unidade_empresa = forms.ChoiceField(
        required=False,
        choices=WEBMANIA_UNIDADE_EMPRESA_CHOICES,
        widget=SearchableSelectInput(choices=WEBMANIA_UNIDADE_EMPRESA_CHOICES),
    )
    workshop_is_active = forms.BooleanField(
        required=False,
        label=Workshop.is_active.field.verbose_name,
        widget=CheckboxInput(),
    )

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
            "contabilidade",
            "logomarca",
        ]
        widgets = {
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "cpf": CPForCNPJInput(mode="cpf"),
            "email": EmailInput(),
            "telefone": PhoneInput(),
            "razao_social": TextInput(),
            "nome_completo": TextInput(),
            "nome_fantasia": TextInput(),
            "ie": TextInput(),
            "im": TextInput(),
            "contabilidade": TextInput(),
            "logomarca": TextInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, workshop=workshop, **kwargs)
        self.fields["email"].required = True
        self.fields["logomarca"].disabled = True
        self.fields["logomarca"].help_text = "A URL da logomarca e sincronizada automaticamente com o upload da logo da oficina."
        if self.workshop is not None:
            self.initial["workshop_is_active"] = bool(self.workshop.is_active)

    def clean(self) -> dict[str, Any]:
        cleaned_data_raw = super().clean()
        cleaned_data: dict[str, Any] = dict(cleaned_data_raw or {})

        cnpj = str(cleaned_data.get("cnpj") or "").strip()
        cpf = str(cleaned_data.get("cpf") or "").strip()
        razao_social = str(cleaned_data.get("razao_social") or "").strip()
        nome_completo = str(cleaned_data.get("nome_completo") or "").strip()

        has_pj_data = bool(cnpj or razao_social)
        has_pf_data = bool(cpf or nome_completo)

        if not has_pj_data and not has_pf_data:
            message = "Preencha CNPJ + Razao Social ou CPF + Nome Completo."
            self.add_error("cnpj", message)
            self.add_error("cpf", message)
            self.add_error("razao_social", message)
            self.add_error("nome_completo", message)
            return cleaned_data

        if has_pj_data:
            if not cnpj:
                self.add_error("cnpj", "Ao informar Razao Social, o CNPJ e obrigatorio.")
            if not razao_social:
                self.add_error("razao_social", "Ao informar CNPJ, a Razao Social e obrigatoria.")
            return cleaned_data

        if not cpf:
            self.add_error("cpf", "Ao informar Nome Completo, o CPF e obrigatorio.")
        if not nome_completo:
            self.add_error("nome_completo", "Ao informar CPF, o Nome Completo e obrigatorio.")

        return cleaned_data

    def save(self, commit: bool = True) -> WebmaniaCompany:
        instance = super().save(commit=commit)

        if commit and self.workshop is not None:
            workshop_is_active = bool(self.cleaned_data.get("workshop_is_active"))
            if self.workshop.is_active != workshop_is_active:
                self.workshop.is_active = workshop_is_active
                self.workshop.save(update_fields=["is_active"])

        return instance


class WorkshopLogoForm(CoreForm):
    logo = forms.FileField(
        required=False,
        label="Logo da oficina",
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp", "svg"], message="Permitido logomarca somente nos formatos JPEG, PNG, WEBP ou SVG.")],
        widget=ImageInput(),
    )

    def __init__(self, *args, instance: Workshop, preview_url: str = "", **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)

        if preview_url:
            self.initial["logo"] = _PreviewableFileValue(preview_url)

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo in (None, False):
            return logo

        allowed_content_types = {"image/jpeg", "image/png", "image/webp", "image/svg+xml"}
        content_type = str(getattr(logo, "content_type", "") or "").strip().lower()
        if content_type and content_type not in allowed_content_types:
            raise forms.ValidationError("Permitido logomarca somente nos formatos JPEG, PNG, WEBP ou SVG.")

        return logo

    def has_new_upload(self) -> bool:
        uploaded_file = self.cleaned_data.get("logo")
        return uploaded_file not in (None, False)

    def should_clear(self) -> bool:
        return self.cleaned_data.get("logo") is False


class WorkshopAddressSectionForm(BaseWebmaniaCompanySectionForm):
    class Meta:
        model = WebmaniaCompany
        fields = [
            "cep",
            "endereco",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
        ]
        widgets = {
            "cep": CEPInput(),
            "endereco": TextInput(),
            "numero": TextInput(),
            "complemento": TextInput(),
            "bairro": TextInput(),
            "cidade": TextInput(),
            "uf": TextInput(),
        }


class WorkshopFiscalSectionForm(BaseWebmaniaCompanySectionForm):
    class Meta:
        model = WebmaniaCompany
        fields = [
            "informacoes_fisco",
            "nfe_serie",
            "nfe_numero",
            "nfe_numero_dev",
            "nfce_serie",
            "nfce_numero",
            "nfce_id_csc",
            "nfce_codigo_csc",
            "nfce_numero_dev",
            "nfce_id_csc_dev",
            "nfce_codigo_csc_dev",
            "nfse_rps_serie",
            "nfse_rps_numero",
            "nfse_lote_rps_numero",
            "nfse_rps_numero_dev",
            "cnae_issqn",
            "cnae",
            "regime_apuracao_sn",
            "regime_especial_nacional",
            "regime_especial_municipal",
        ]
        widgets = {
            "informacoes_fisco": TextareaInput(rows=3),
            "nfe_serie": NumberInput(),
            "nfe_numero": NumberInput(),
            "nfe_numero_dev": NumberInput(),
            "nfce_serie": NumberInput(),
            "nfce_numero": NumberInput(),
            "nfce_id_csc": TextInput(),
            "nfce_codigo_csc": TextInput(),
            "nfce_numero_dev": NumberInput(),
            "nfce_id_csc_dev": TextInput(),
            "nfce_codigo_csc_dev": TextInput(),
            "nfse_rps_serie": TextInput(),
            "nfse_rps_numero": NumberInput(),
            "nfse_lote_rps_numero": NumberInput(),
            "nfse_rps_numero_dev": NumberInput(),
            "cnae_issqn": TextInput(),
            "cnae": TextInput(),
            "regime_apuracao_sn": TextInput(),
            "regime_especial_nacional": TextInput(),
            "regime_especial_municipal": TextInput(),
        }


class WorkshopOptionalsSectionForm(BaseWebmaniaCompanySectionForm):
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

    orientacao_danfe = forms.ChoiceField(
        required=False,
        choices=WEBMANIA_ORIENTACAO_DANFE_CHOICES,
        widget=SearchableSelectInput(choices=WEBMANIA_ORIENTACAO_DANFE_CHOICES),
    )
    desativar_epec = forms.ChoiceField(
        required=False,
        choices=WEBMANIA_ENABLED_FLAG_CHOICES,
        widget=SearchableSelectInput(choices=WEBMANIA_ENABLED_FLAG_CHOICES),
    )
    ocultar_total_etiqueta = forms.ChoiceField(
        required=False,
        choices=WEBMANIA_ENABLED_FLAG_CHOICES,
        widget=SearchableSelectInput(choices=WEBMANIA_ENABLED_FLAG_CHOICES),
    )

    class Meta:
        model = WebmaniaCompany
        fields = [
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


class WorkshopPdfObservationSectionForm(CoreModelForm):
    class Meta:
        model = Workshop
        fields = ["pdf_observation"]
        widgets = {
            "pdf_observation": TextareaInput(
                attrs={
                    "rows": 5,
                    "placeholder": "Texto fixo que aparece em todos os PDFs de orcamento.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("pdf_observation")
        if field is not None:
            field.label = "Observacao fixa do PDF"
            field.help_text = "Exibida no PDF abaixo das observacoes do orcamento."


class WorkshopCertificateSectionForm(CoreForm):
    pfx_certificate = forms.FileField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=["pfx", "p12"])],
        widget=forms.FileInput(attrs={"accept": ".pfx,.p12,application/x-pkcs12"}),
    )
    certificate_password = forms.CharField(required=False, widget=PasswordInput(render_value=True))

    def __init__(self, *args, instance: Workshop, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.initial["certificate_password"] = str(instance.certificate_password or "")

        certificate_field = self.fields.get("pfx_certificate")
        if certificate_field is not None:
            certificate_field.label = "Novo certificado A1 (.pfx ou .p12)"
            certificate_field.help_text = "Escolha o arquivo do certificado. Se ja existir um arquivo salvo, o novo upload vai substituir o atual."

        password_field = self.fields.get("certificate_password")
        if password_field is not None:
            password_field.help_text = "Informe a senha do certificado para concluir a configuracao."

    def clean(self) -> dict[str, Any]:
        cleaned_data = dict(super().clean() or {})
        uploaded_certificate = cleaned_data.get("pfx_certificate")
        certificate_password = str(cleaned_data.get("certificate_password") or "").strip()
        current_password = str(self.instance.certificate_password or "").strip()
        has_existing_certificate = bool(self.instance.has_certificate_file)
        resolved_password = certificate_password or current_password

        if uploaded_certificate is not None and not resolved_password:
            self.add_error("certificate_password", "Informe a senha do certificado para concluir a configuracao.")

        if has_existing_certificate and "certificate_password" in self.changed_data and not certificate_password:
            self.add_error("certificate_password", "A senha nao pode ficar vazia enquanto existir um certificado ativo.")

        return cleaned_data

    def has_new_upload(self) -> bool:
        return self.cleaned_data.get("pfx_certificate") is not None
