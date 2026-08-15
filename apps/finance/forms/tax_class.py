from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms
from django.forms import formset_factory

from apps.core.presentation.widgets import CheckboxInput, DecimalInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.models import TaxClassPreset
from apps.core.presentation.forms import CoreForm, CoreModelForm
from apps.finance.services.tax_classes import (
    NFSE_CODIGO_SERVICO_HELP_TEXT,
    NFSE_CODIGO_SERVICO_INVALID_FORMAT,
    format_nfse_service_code_for_api,
    is_valid_nfse_service_code,
)


NFE_SCENARIO_CHOICES = (
    ("", "Selecione"),
    ("saida_dentro_estado", "Saída dentro do estado"),
    ("saida_fora_estado", "Saída fora do estado"),
    ("saida_exterior", "Saída para o exterior"),
    ("entrada_dentro_estado", "Entrada dentro do estado"),
    ("entrada_fora_estado", "Entrada fora do estado"),
    ("entrada_exterior", "Entrada do exterior"),
)

SCENARIO_PADRAO_CHOICES = (("", "Selecione"), ("padrao", "Padrão"), *NFE_SCENARIO_CHOICES[1:])

TIPO_PESSOA_CHOICES = (("", "Selecione"), ("fisica", "Física"), ("juridica", "Jurídica"), ("estrangeira", "Estrangeira"))

ICMS_TIPO_TRIBUTACAO_CHOICES = (
    ("", "Selecione"),
    ("simples_nacional", "Simples Nacional"),
    ("simples_nacional_sublimite", "Simples Nacional Sublimite"),
    ("tributacao_normal", "Tributação Normal"),
)

NATUREZA_OPERACAO_CHOICES = (
    ("", "Selecione"),
    ("1", "Tributação no município"),
    ("2", "Tributação fora do município"),
    ("3", "Isenção"),
    ("4", "Imune"),
    ("5", "Exigibilidade suspensa por decisão judicial"),
    ("6", "Exigibilidade suspensa por procedimento administrativo"),
)

EXIGIBILIDADE_ISS_CHOICES = (
    ("", "Selecione"),
    ("1", "Exigível"),
    ("2", "Não incidência"),
    ("3", "Isenção"),
    ("4", "Exportação"),
    ("5", "Imunidade"),
    ("6", "Exigibilidade suspensa por decisão judicial"),
    ("7", "Exigibilidade suspensa por processo administrativo"),
)

ISS_RETIDO_CHOICES = (("", "Selecione"), ("1", "Sim"), ("2", "Não"))
RESPONSAVEL_RETENCAO_CHOICES = (("", "Selecione"), ("1", "Tomador"), ("2", "Intermediário"))

TIPO_EMISSAO_NFSE_CHOICES = (("1", "Normal"),)
TRIBUTACAO_ISS_CHOICES = (("", "Selecione"), ("1", "Operação tributável"), ("2", "Imunidade"), ("4", "Não incidência"))
TIPO_IMUNIDADE_CHOICES = (
    ("", "Selecione"),
    ("0", "Imunidade sem tipo"),
    ("1", "CF88 Art 150 VI a"),
    ("2", "CF88 Art 150 VI b"),
    ("3", "CF88 Art 150 VI c"),
    ("4", "CF88 Art 150 VI d"),
    ("5", "CF88 Art 150 VI e"),
)
RETENCAO_ISS_NACIONAL_CHOICES = (("", "Selecione"), ("1", "Não retido"), ("2", "Retido pelo tomador"), ("3", "Retido pelo intermediário"))
CST_PIS_COFINS_CHOICES = (
    ("00", "00 - Nenhum"),
    ("01", "01 - Alíquota básica"),
    ("06", "06 - Alíquota zero"),
    ("07", "07 - Isenta"),
    ("08", "08 - Sem incidência"),
    ("09", "09 - Suspensão"),
    ("49", "49 - Outras saídas"),
)
RETENCAO_PIS_COFINS_CHOICES = (
    ("0", "0 - Não retidos"),
    ("3", "3 - PIS/COFINS/CSLL retidos"),
    ("4", "4 - PIS/COFINS retidos"),
)


def _format_decimal(value: Decimal, *, places: int = 2) -> str:
    quantizer = Decimal(1).scaleb(-places)
    return f"{value.quantize(quantizer):f}"


class TaxClassFormBase(CoreForm):
    referencia = forms.CharField(
        label="Referência",
        required=False,
        max_length=30,
        help_text="Gerada automaticamente e não pode ser alterada.",
        widget=TextInput(attrs={"readonly": True, "placeholder": "Gerada automaticamente"}),
    )
    descricao = forms.CharField(label="Descrição", required=True, max_length=255, widget=TextInput())
    informacoes_fisco = forms.CharField(label="Informações ao Fisco", required=False, widget=TextareaInput(rows=3))
    informacoes_complementares = forms.CharField(label="Informações complementares", required=False, widget=TextareaInput(rows=3))
    base_payload_json = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean_referencia(self) -> str:
        # Reference is API-generated and immutable; ignore any client-submitted override.
        return str(self.initial.get("referencia") or "").strip()

    def get_base_payload(self) -> dict[str, Any]:
        raw_payload = self.cleaned_data.get("base_payload_json")
        if not raw_payload:
            return {}

        try:
            parsed = json.loads(raw_payload)
        except json.JSONDecodeError:
            return {}

        if isinstance(parsed, dict):
            return parsed
        return {}

    @classmethod
    def initial_from_tax_class(cls, tax_class: dict[str, Any]) -> dict[str, str]:
        payload = dict(tax_class)
        return {
            "referencia": str(payload.get("referencia") or ""),
            "descricao": str(payload.get("descricao") or ""),
            "informacoes_fisco": str(payload.get("informacoes_fisco") or ""),
            "informacoes_complementares": str(payload.get("informacoes_complementares") or ""),
            "base_payload_json": json.dumps(payload, ensure_ascii=False),
        }


class TaxClassPresetMetaForm(CoreModelForm):
    class Meta:
        model = TaxClassPreset
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Revenda padrão oficina"}),
            "description": TextareaInput(rows=3, attrs={"placeholder": "Explique quando este preset deve ser usado."}),
            "is_active": CheckboxInput(),
        }


class NfeTaxClassForm(TaxClassFormBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-xl font-bold'>Dados da classe NF-e</h2>"),
                HTML("<p class='text-base-content/70'>Preencha os dados básicos da classe e configure os cenários abaixo.</p>"),
                Div(
                    Field("referencia", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("descricao", wrapper_class="col-span-12 lg:col-span-8"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Div(
                    Field("informacoes_fisco", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("informacoes_complementares", wrapper_class="col-span-12 lg:col-span-6"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Field("base_payload_json"),
                css_class="space-y-4",
            )
        )


class NfseTaxClassForm(TaxClassFormBase):
    codigo_servico = forms.CharField(
        label="Código do serviço",
        required=True,
        help_text=NFSE_CODIGO_SERVICO_HELP_TEXT,
        widget=TextInput(),
    )
    tipo_emissao = forms.ChoiceField(label="Tipo de emissão", required=False, choices=TIPO_EMISSAO_NFSE_CHOICES, widget=SearchableSelectInput(choices=TIPO_EMISSAO_NFSE_CHOICES))
    codigo_tributacao_municipio = forms.CharField(label="Código de tributação do município", required=False, widget=TextInput())
    tributacao_iss = forms.ChoiceField(label="Tributação ISS", required=False, choices=TRIBUTACAO_ISS_CHOICES, widget=SearchableSelectInput(choices=TRIBUTACAO_ISS_CHOICES))
    tipo_imunidade = forms.ChoiceField(label="Tipo de imunidade", required=False, choices=TIPO_IMUNIDADE_CHOICES, widget=SearchableSelectInput(choices=TIPO_IMUNIDADE_CHOICES))
    retencao_iss = forms.ChoiceField(label="Retenção ISS", required=False, choices=RETENCAO_ISS_NACIONAL_CHOICES, widget=SearchableSelectInput(choices=RETENCAO_ISS_NACIONAL_CHOICES))
    cst_pis_cofins = forms.ChoiceField(label="CST PIS/COFINS", required=False, choices=CST_PIS_COFINS_CHOICES, widget=SearchableSelectInput(choices=CST_PIS_COFINS_CHOICES))
    retencao_pis_cofins = forms.ChoiceField(label="Retenção PIS/COFINS", required=False, choices=RETENCAO_PIS_COFINS_CHOICES, widget=SearchableSelectInput(choices=RETENCAO_PIS_COFINS_CHOICES))

    natureza_operacao = forms.ChoiceField(label="Natureza da operação (ABRASF)", required=False, choices=NATUREZA_OPERACAO_CHOICES, widget=SearchableSelectInput(choices=NATUREZA_OPERACAO_CHOICES))
    exigibilidade_iss = forms.ChoiceField(label="Exigibilidade ISS (ABRASF)", required=True, choices=EXIGIBILIDADE_ISS_CHOICES, widget=SearchableSelectInput(choices=EXIGIBILIDADE_ISS_CHOICES))
    iss_retido = forms.ChoiceField(label="ISS retido (ABRASF)", required=True, choices=ISS_RETIDO_CHOICES, widget=SearchableSelectInput(choices=ISS_RETIDO_CHOICES))
    responsavel_retencao = forms.ChoiceField(label="Responsável pela retenção", required=False, choices=RESPONSAVEL_RETENCAO_CHOICES, widget=SearchableSelectInput(choices=RESPONSAVEL_RETENCAO_CHOICES))
    codigo_cnae = forms.CharField(label="Código CNAE", required=False, widget=TextInput())

    iss = forms.DecimalField(label="Alíquota ISS", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    pis = forms.DecimalField(label="Alíquota PIS", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    cofins = forms.DecimalField(label="Alíquota COFINS", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    inss = forms.DecimalField(label="Alíquota INSS", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    ir = forms.DecimalField(label="Alíquota IR", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    csll = forms.DecimalField(label="Alíquota CSLL", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

    ibs_situacao_tributaria = forms.CharField(label="IBS/CBS Situação tributária", required=False, widget=TextInput())
    ibs_classificacao_tributaria = forms.CharField(label="IBS/CBS Classificação tributária", required=False, widget=TextInput())
    ibs_situacao_tributaria_regular = forms.CharField(label="IBS/CBS Situação tributária regular", required=False, widget=TextInput())
    ibs_classificacao_tributaria_regular = forms.CharField(label="IBS/CBS Classificação tributária regular", required=False, widget=TextInput())
    ibs_credito_presumido = forms.CharField(label="IBS/CBS Crédito presumido", required=False, widget=TextInput())
    ibs_aliquota_diferimento_estadual = forms.DecimalField(label="Diferimento IBS estadual (%)", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    ibs_aliquota_diferimento_municipal = forms.DecimalField(label="Diferimento IBS municipal (%)", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    cbs_aliquota_diferimento = forms.DecimalField(label="Diferimento CBS (%)", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

    @classmethod
    def initial_from_tax_class(cls, tax_class: dict[str, Any]) -> dict[str, str]:
        initial = super().initial_from_tax_class(tax_class)
        payload = dict(tax_class)

        for field_name in (
            "tipo_emissao",
            "codigo_servico",
            "codigo_tributacao_municipio",
            "tributacao_iss",
            "tipo_imunidade",
            "retencao_iss",
            "cst_pis_cofins",
            "retencao_pis_cofins",
            "natureza_operacao",
            "exigibilidade_iss",
            "iss_retido",
            "responsavel_retencao",
            "codigo_cnae",
            "iss",
            "pis",
            "cofins",
            "inss",
            "ir",
            "csll",
        ):
            if field_name in payload and payload.get(field_name) not in (None, ""):
                value = payload.get(field_name)
                if field_name == "codigo_servico":
                    initial[field_name] = format_nfse_service_code_for_api(value)
                else:
                    initial[field_name] = str(value)

        ibs_cbs_payload = payload.get("ibs_cbs")
        if isinstance(ibs_cbs_payload, dict):
            field_map = {
                "situacao_tributaria": "ibs_situacao_tributaria",
                "classificacao_tributaria": "ibs_classificacao_tributaria",
                "situacao_tributaria_regular": "ibs_situacao_tributaria_regular",
                "classificacao_tributaria_regular": "ibs_classificacao_tributaria_regular",
                "credito_presumido": "ibs_credito_presumido",
            }
            for payload_key, field_name in field_map.items():
                value = ibs_cbs_payload.get(payload_key)
                if value not in (None, ""):
                    initial[field_name] = str(value)

            for payload_key, field_name in (
                ("ibs_estadual", "ibs_aliquota_diferimento_estadual"),
                ("ibs_municipal", "ibs_aliquota_diferimento_municipal"),
                ("cbs", "cbs_aliquota_diferimento"),
            ):
                value = ibs_cbs_payload.get(payload_key)
                if isinstance(value, dict) and value.get("aliquota_diferimento") not in (None, ""):
                    initial[field_name] = str(value.get("aliquota_diferimento"))

        return initial

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault("natureza_operacao", "1")
            self.initial.setdefault("exigibilidade_iss", "1")
            self.initial.setdefault("iss_retido", "2")

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-xl font-bold'>Dados da classe NFS-e</h2>"),
                Div(
                    Field("referencia", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("descricao", wrapper_class="col-span-12 lg:col-span-8"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Div(
                    Field("tipo_emissao", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("codigo_servico", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("codigo_tributacao_municipio", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("tributacao_iss", wrapper_class="col-span-12 lg:col-span-3"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Div(
                    Field("tipo_imunidade", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("retencao_iss", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("cst_pis_cofins", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Field("retencao_pis_cofins"),
                HTML("<h3 class='font-semibold mt-2'>Campos específicos de provedor (opcional)</h3>"),
                Div(
                    Field("natureza_operacao", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("exigibilidade_iss", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("iss_retido", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("responsavel_retencao", wrapper_class="col-span-12 lg:col-span-3"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Div(
                    Field("codigo_cnae", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-12 gap-4 items-end",
                ),
                Div(
                    Field("iss", wrapper_class="col-span-12 sm:col-span-6 lg:col-span-2"),
                    Field("pis", wrapper_class="col-span-12 sm:col-span-6 lg:col-span-2"),
                    Field("cofins", wrapper_class="col-span-12 sm:col-span-6 lg:col-span-2"),
                    Field("inss", wrapper_class="col-span-12 sm:col-span-6 lg:col-span-2"),
                    Field("ir", wrapper_class="col-span-12 sm:col-span-6 lg:col-span-2"),
                    Field("csll", wrapper_class="col-span-12 sm:col-span-6 lg:col-span-2"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                HTML("<h3 class='font-semibold mt-2'>IBS/CBS (opcional)</h3>"),
                Div(
                    Field("ibs_situacao_tributaria", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("ibs_classificacao_tributaria", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("ibs_situacao_tributaria_regular", wrapper_class="col-span-12 lg:col-span-3"),
                    Field("ibs_classificacao_tributaria_regular", wrapper_class="col-span-12 lg:col-span-3"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Div(
                    Field("ibs_credito_presumido", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("ibs_aliquota_diferimento_estadual", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("ibs_aliquota_diferimento_municipal", wrapper_class="col-span-12 lg:col-span-4"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Field("cbs_aliquota_diferimento"),
                Div(
                    Field("informacoes_fisco", wrapper_class="col-span-12 lg:col-span-6"),
                    Field("informacoes_complementares", wrapper_class="col-span-12 lg:col-span-6"),
                    css_class="grid grid-cols-12 gap-4",
                ),
                Field("base_payload_json"),
                css_class="space-y-4",
            )
        )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}

        codigo_servico = format_nfse_service_code_for_api(cleaned_data.get("codigo_servico"))
        if codigo_servico and not is_valid_nfse_service_code(codigo_servico):
            self.add_error("codigo_servico", NFSE_CODIGO_SERVICO_INVALID_FORMAT)
        elif codigo_servico:
            cleaned_data["codigo_servico"] = codigo_servico

        if cleaned_data.get("tributacao_iss") == "2" and not cleaned_data.get("tipo_imunidade"):
            self.add_error("tipo_imunidade", "Informe o tipo de imunidade quando a tributação do ISS for Imunidade.")

        iss_retido = cleaned_data.get("iss_retido")
        responsavel_retencao = cleaned_data.get("responsavel_retencao")

        if iss_retido == "1" and not responsavel_retencao:
            self.add_error("responsavel_retencao", "Informe o responsável pela retenção quando o ISS for retido.")

        if iss_retido != "1" and responsavel_retencao:
            self.add_error("responsavel_retencao", "Preencha apenas quando o ISS for retido.")

        has_service_tax_data = any(
            cleaned_data.get(field_name) not in (None, "")
            for field_name in (
                "natureza_operacao",
                "exigibilidade_iss",
                "iss_retido",
                "iss",
                "pis",
                "cofins",
                "inss",
                "ir",
                "csll",
            )
        )

        if has_service_tax_data and not cleaned_data.get("codigo_servico"):
            self.add_error("codigo_servico", "Informe o código do serviço para utilizar os campos de tributação.")

        return cleaned_data

    def build_payload(self) -> dict[str, Any]:
        payload = self.get_base_payload()
        payload["tipo"] = "nfse"

        text_fields = (
            "referencia",
            "descricao",
            "tipo_emissao",
            "codigo_servico",
            "codigo_tributacao_municipio",
            "tributacao_iss",
            "tipo_imunidade",
            "retencao_iss",
            "cst_pis_cofins",
            "retencao_pis_cofins",
            "natureza_operacao",
            "exigibilidade_iss",
            "iss_retido",
            "responsavel_retencao",
            "codigo_cnae",
            "informacoes_fisco",
            "informacoes_complementares",
        )
        for field_name in text_fields:
            value = self.cleaned_data.get(field_name)
            if value in (None, ""):
                payload.pop(field_name, None)
                continue
            payload[field_name] = str(value).strip()

        for field_name in ("iss", "pis", "cofins", "inss", "ir", "csll"):
            value = self.cleaned_data.get(field_name)
            if value is None:
                payload.pop(field_name, None)
                continue
            payload[field_name] = _format_decimal(value, places=2)

        ibs_cbs_payload = dict(payload.get("ibs_cbs") or {})
        for field_name, payload_key in (
            ("ibs_situacao_tributaria", "situacao_tributaria"),
            ("ibs_classificacao_tributaria", "classificacao_tributaria"),
            ("ibs_situacao_tributaria_regular", "situacao_tributaria_regular"),
            ("ibs_classificacao_tributaria_regular", "classificacao_tributaria_regular"),
            ("ibs_credito_presumido", "credito_presumido"),
        ):
            value = self.cleaned_data.get(field_name)
            if value in (None, ""):
                ibs_cbs_payload.pop(payload_key, None)
                continue
            ibs_cbs_payload[payload_key] = str(value).strip()

        differimento_map = (
            ("ibs_aliquota_diferimento_estadual", "ibs_estadual"),
            ("ibs_aliquota_diferimento_municipal", "ibs_municipal"),
            ("cbs_aliquota_diferimento", "cbs"),
        )
        for field_name, payload_key in differimento_map:
            value = self.cleaned_data.get(field_name)
            if value is None:
                ibs_cbs_payload.pop(payload_key, None)
                continue
            ibs_cbs_payload[payload_key] = {"aliquota_diferimento": float(value)}

        if ibs_cbs_payload:
            payload["ibs_cbs"] = ibs_cbs_payload
        else:
            payload.pop("ibs_cbs", None)

        return payload


class ScenarioFormBase(CoreForm):
    source_index = forms.IntegerField(required=False, widget=forms.HiddenInput())

    payload_fields: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    decimal_fields: dict[str, int] = {}

    def __init__(self, *args, **kwargs):
        kwargs["empty_permitted"] = False
        super().__init__(*args, **kwargs)

    @staticmethod
    def _validate_tipo_pessoa_by_cenario(form: "ScenarioFormBase", cleaned_data: dict[str, Any]) -> None:
        cenario = str(cleaned_data.get("cenario") or "")
        tipo_pessoa = str(cleaned_data.get("tipo_pessoa") or "")
        if not cenario or not tipo_pessoa:
            return

        if cenario == "saida_exterior" and tipo_pessoa != "estrangeira":
            form.add_error("tipo_pessoa", "Para cenário de saída para o exterior, o tipo de pessoa deve ser Estrangeira.")

        if cenario not in {"saida_exterior", "padrao"} and tipo_pessoa == "estrangeira":
            form.add_error("tipo_pessoa", "Tipo de pessoa estrangeira é válido apenas para cenário de saída para o exterior ou padrão.")

    def _is_empty_row(self, cleaned_data: dict[str, Any]) -> bool:
        for field_name in self.payload_fields:
            value = cleaned_data.get(field_name)
            if isinstance(value, bool):
                if value:
                    return False
                continue
            if value not in (None, ""):
                return False
        return True

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        for field_name in self.required_fields:
            if cleaned_data.get(field_name) in (None, ""):
                self.add_error(field_name, "Campo obrigatório para este cenário.")

        cleaned_data["_is_empty"] = self._is_empty_row(cleaned_data)
        return cleaned_data

    def to_payload(self) -> tuple[dict[str, Any], int | None]:
        payload: dict[str, Any] = {}
        for field_name in self.payload_fields:
            value = self.cleaned_data.get(field_name)
            if value in (None, ""):
                continue

            if isinstance(value, Decimal):
                places = self.decimal_fields.get(field_name, 2)
                payload[field_name] = _format_decimal(value, places=places)
                continue

            if isinstance(value, bool):
                if value:
                    payload[field_name] = True
                continue

            payload[field_name] = str(value).strip()

        source_index_value = self.cleaned_data.get("source_index")
        return payload, source_index_value


class IcmsScenarioForm(ScenarioFormBase):
    tipo_tributacao = forms.ChoiceField(label="Tipo de tributação", required=False, choices=ICMS_TIPO_TRIBUTACAO_CHOICES, widget=SearchableSelectInput(choices=ICMS_TIPO_TRIBUTACAO_CHOICES))
    cenario = forms.ChoiceField(label="Cenário", required=False, choices=NFE_SCENARIO_CHOICES, widget=SearchableSelectInput(choices=NFE_SCENARIO_CHOICES))
    tipo_pessoa = forms.ChoiceField(label="Tipo de pessoa", required=False, choices=TIPO_PESSOA_CHOICES, widget=SearchableSelectInput(choices=TIPO_PESSOA_CHOICES))
    nao_contribuinte = forms.BooleanField(label="Não contribuinte", required=False, widget=CheckboxInput())
    codigo_cfop = forms.CharField(label="CFOP", required=False, max_length=10, widget=TextInput())
    situacao_tributaria = forms.CharField(label="Situação tributária", required=False, max_length=3, widget=TextInput())
    aliquota_credito = forms.DecimalField(label="Alíquota de crédito", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    aliquota_importacao = forms.DecimalField(label="Alíquota de importação", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

    payload_fields = (
        "tipo_tributacao",
        "cenario",
        "tipo_pessoa",
        "nao_contribuinte",
        "codigo_cfop",
        "situacao_tributaria",
        "aliquota_credito",
        "aliquota_importacao",
    )
    required_fields = ("tipo_tributacao", "cenario", "tipo_pessoa", "codigo_cfop", "situacao_tributaria")
    decimal_fields = {
        "aliquota_credito": 2,
        "aliquota_importacao": 2,
    }

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data.get("_is_empty"):
            return cleaned_data

        cenario = str(cleaned_data.get("cenario") or "")
        tipo_pessoa = str(cleaned_data.get("tipo_pessoa") or "")
        situacao_tributaria = str(cleaned_data.get("situacao_tributaria") or "")

        if cenario == "entrada_exterior" and cleaned_data.get("aliquota_importacao") in (None, ""):
            self.add_error("aliquota_importacao", "Obrigatório para cenário de importação (entrada do exterior).")

        if situacao_tributaria in {"101", "201"} and cleaned_data.get("aliquota_credito") in (None, ""):
            self.add_error("aliquota_credito", "Obrigatório para CST 101 ou 201.")

        if cleaned_data.get("nao_contribuinte") and tipo_pessoa != "juridica":
            self.add_error("nao_contribuinte", "Use esta opção apenas para destinatário pessoa jurídica.")

        if cenario == "saida_exterior" and tipo_pessoa != "estrangeira":
            self.add_error("tipo_pessoa", "Para cenário de saída para o exterior, o tipo de pessoa deve ser Estrangeira.")

        if cenario != "saida_exterior" and tipo_pessoa == "estrangeira":
            self.add_error("tipo_pessoa", "Tipo de pessoa estrangeira é válido apenas para cenário de saída para o exterior.")

        codigo_cfop = str(cleaned_data.get("codigo_cfop") or "")
        if codigo_cfop:
            digits = "".join(char for char in codigo_cfop if char.isdigit())
            if len(digits) != 4:
                self.add_error("codigo_cfop", "O CFOP deve conter 4 dígitos.")

        return cleaned_data


class IpiScenarioForm(ScenarioFormBase):
    cenario = forms.ChoiceField(label="Cenário", required=False, choices=SCENARIO_PADRAO_CHOICES, widget=SearchableSelectInput(choices=SCENARIO_PADRAO_CHOICES))
    tipo_pessoa = forms.ChoiceField(label="Tipo de pessoa", required=False, choices=TIPO_PESSOA_CHOICES, widget=SearchableSelectInput(choices=TIPO_PESSOA_CHOICES))
    situacao_tributaria = forms.CharField(label="Situação tributária", required=False, max_length=3, widget=TextInput())
    codigo_enquadramento = forms.CharField(label="Código de enquadramento", required=False, max_length=3, widget=TextInput())
    aliquota = forms.DecimalField(label="Alíquota", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

    payload_fields = ("cenario", "tipo_pessoa", "situacao_tributaria", "codigo_enquadramento", "aliquota")
    required_fields = ("cenario", "tipo_pessoa", "situacao_tributaria", "codigo_enquadramento", "aliquota")
    decimal_fields = {"aliquota": 2}

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data.get("_is_empty"):
            return cleaned_data

        self._validate_tipo_pessoa_by_cenario(self, cleaned_data)
        return cleaned_data


class PisScenarioForm(ScenarioFormBase):
    cenario = forms.ChoiceField(label="Cenário", required=False, choices=SCENARIO_PADRAO_CHOICES, widget=SearchableSelectInput(choices=SCENARIO_PADRAO_CHOICES))
    tipo_pessoa = forms.ChoiceField(label="Tipo de pessoa", required=False, choices=TIPO_PESSOA_CHOICES, widget=SearchableSelectInput(choices=TIPO_PESSOA_CHOICES))
    situacao_tributaria = forms.CharField(label="Situação tributária", required=False, max_length=3, widget=TextInput())
    aliquota = forms.DecimalField(label="Alíquota", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

    payload_fields = ("cenario", "tipo_pessoa", "situacao_tributaria", "aliquota")
    required_fields = ("cenario", "tipo_pessoa", "situacao_tributaria", "aliquota")
    decimal_fields = {"aliquota": 2}

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data.get("_is_empty"):
            return cleaned_data

        self._validate_tipo_pessoa_by_cenario(self, cleaned_data)
        return cleaned_data


class CofinsScenarioForm(ScenarioFormBase):
    cenario = forms.ChoiceField(label="Cenário", required=False, choices=SCENARIO_PADRAO_CHOICES, widget=SearchableSelectInput(choices=SCENARIO_PADRAO_CHOICES))
    tipo_pessoa = forms.ChoiceField(label="Tipo de pessoa", required=False, choices=TIPO_PESSOA_CHOICES, widget=SearchableSelectInput(choices=TIPO_PESSOA_CHOICES))
    situacao_tributaria = forms.CharField(label="Situação tributária", required=False, max_length=3, widget=TextInput())
    aliquota = forms.DecimalField(label="Alíquota", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

    payload_fields = ("cenario", "tipo_pessoa", "situacao_tributaria", "aliquota")
    required_fields = ("cenario", "tipo_pessoa", "situacao_tributaria", "aliquota")
    decimal_fields = {"aliquota": 2}

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data.get("_is_empty"):
            return cleaned_data

        self._validate_tipo_pessoa_by_cenario(self, cleaned_data)
        return cleaned_data


IcmsScenarioFormSet = formset_factory(IcmsScenarioForm, extra=0, can_delete=True)
IpiScenarioFormSet = formset_factory(IpiScenarioForm, extra=0, can_delete=True)
PisScenarioFormSet = formset_factory(PisScenarioForm, extra=0, can_delete=True)
CofinsScenarioFormSet = formset_factory(CofinsScenarioForm, extra=0, can_delete=True)
