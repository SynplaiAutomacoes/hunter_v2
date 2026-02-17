from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django import forms
from django.forms import formset_factory
from django.urls import reverse

from apps.core.widgets import CEPInput, CPForCNPJInput, CheckboxInput, DecimalInput, EmailInput, PasswordInput, PhoneInput, SelectInput, TextInput, TextareaInput
from apps.finance.models import NfseRequest, WebmaniaCompany, WebmaniaCompanyTaxType
from apps.finance.services.webmania_secrets import encrypt_secret
from apps.workorder.models import WorkOrder, WorkOrderStatus


def _format_money(value: Any) -> str:
    amount: Decimal
    if hasattr(value, "amount"):
        amount = value.amount
    else:
        amount = Decimal(str(value))

    return f"R$ {amount:.2f}".replace(".", ",")


def _collect_service_rows(workorder: WorkOrder) -> tuple[list[dict[str, Any]], str, str]:
    budget = workorder.budget
    rows: list[dict[str, Any]] = []

    items = budget.items.select_related("service", "kit").all()
    for item in items:
        if item.service or (item.is_local and item.service_selling_price.amount > 0):
            total_value = item.service_selling_price * item.quantity
            rows.append(
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_value": item.service_selling_price,
                    "total_value": total_value,
                }
            )
            continue

        if item.kit:
            kit_services_total = item.get_kit_services_total()
            if kit_services_total.amount <= 0:
                continue

            rows.append(
                {
                    "description": f"{item.description} (Serviços do Kit)",
                    "quantity": item.quantity,
                    "unit_value": kit_services_total,
                    "total_value": kit_services_total,
                }
            )

    total_services = budget.total_services_value
    total_services_formatted = _format_money(total_services)

    if rows:
        default_description = "; ".join(f"{row['quantity']}x {row['description']}" for row in rows)
    else:
        default_description = f"Prestação de serviço referente à OS #{workorder.pk}"

    return rows, total_services_formatted, default_description


class NfseRequestStep1Form(forms.ModelForm):
    class Meta:
        model = NfseRequest
        fields = ["workorder"]

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        queryset = WorkOrder.objects.none()
        if workshop is not None:
            queryset = WorkOrder.objects.filter(workshop=workshop, status=WorkOrderStatus.APPROVED).select_related("budget", "budget__customer", "budget__vehicle")

        field = self.fields["workorder"]
        field.queryset = queryset.order_by("-id")

        def _label_from_instance(workorder: WorkOrder) -> str:
            customer = getattr(getattr(workorder, "budget", None), "customer", None)
            customer_name = customer.name if customer else "Cliente não informado"
            return f"Ordem de Serviço - {customer_name} - #{workorder.pk}"

        field.label_from_instance = _label_from_instance
        field.widget = SelectInput(choices=field.choices)
        field.label = "Ordem de Serviço"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Selecionar Ordem de Serviço</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Selecione a ordem de serviço aprovada que será utilizada para emitir a NFS-e.</p>"),
                Field("workorder"),
                css_class="space-y-4",
            )
        )


class NfseRequestStep2Form(forms.ModelForm):
    class Meta:
        model = NfseRequest
        fields: list[str] = []

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        customer = None
        vehicle = None
        if self.instance and self.instance.workorder_id:
            budget = self.instance.workorder.budget
            customer = budget.customer
            vehicle = budget.vehicle

        customer_name = escape(customer.name) if customer else "Não informado"
        customer_doc = escape(customer.cpf_or_cnpj_formatted) if customer else "Não informado"
        customer_phone = escape(str(customer.phone)) if customer and customer.phone else "Não informado"
        customer_email = escape(customer.email) if customer and customer.email else "Não informado"
        customer_address = escape(customer.full_address) if customer else "Não informado"
        vehicle_label = escape(str(vehicle)) if vehicle else "Não informado"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir dados do cliente</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Valide os dados do cliente antes de avançar para a etapa de emissão.</p>"),
                HTML(
                    f"""
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-base-200 p-5 rounded-xl">
                        <div>
                            <p class="text-xs uppercase text-base-content/60">Cliente</p>
                            <p class="font-semibold">{customer_name}</p>
                        </div>
                        <div>
                            <p class="text-xs uppercase text-base-content/60">Documento</p>
                            <p class="font-semibold">{customer_doc}</p>
                        </div>
                        <div>
                            <p class="text-xs uppercase text-base-content/60">Telefone</p>
                            <p class="font-semibold">{customer_phone}</p>
                        </div>
                        <div>
                            <p class="text-xs uppercase text-base-content/60">E-mail</p>
                            <p class="font-semibold">{customer_email}</p>
                        </div>
                        <div class="md:col-span-2">
                            <p class="text-xs uppercase text-base-content/60">Endereço</p>
                            <p class="font-semibold">{customer_address}</p>
                        </div>
                        <div class="md:col-span-2">
                            <p class="text-xs uppercase text-base-content/60">Veículo</p>
                            <p class="font-semibold">{vehicle_label}</p>
                        </div>
                    </div>
                    """
                ),
                css_class="space-y-4",
            )
        )


class NfseRequestStep3Form(forms.ModelForm):
    class Meta:
        model = NfseRequest
        fields = ["tax_class", "service_description"]
        widgets = {
            "tax_class": TextInput(),
            "service_description": TextareaInput(rows=4),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.tax_class_choices = kwargs.pop("tax_class_choices", [])
        super().__init__(*args, **kwargs)

        tax_class_field = self.fields["tax_class"]
        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(self.tax_class_choices)
        tax_class_field.widget = SelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe de imposto de servico (NFS-e)."
        self._valid_tax_class_refs = {value for value, _ in self.tax_class_choices if value}

        current_tax_class = str(getattr(self.instance, "tax_class", "") or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs:
            default_tax_class = next(iter(self._valid_tax_class_refs))
            self.initial["tax_class"] = default_tax_class

        rows: list[dict[str, Any]] = []
        total_services_formatted = _format_money(0)
        default_description = "Prestação de serviço"

        if self.instance and self.instance.workorder_id:
            rows, total_services_formatted, default_description = _collect_service_rows(self.instance.workorder)

        if not self.instance.service_description:
            self.initial["service_description"] = default_description

        rows_html = "".join(
            f"""
            <tr class="border-b border-base-300/60">
                <td class="py-2">{escape(str(row["description"]))}</td>
                <td class="py-2 text-center">{row["quantity"]}</td>
                <td class="py-2 text-right">{_format_money(row["unit_value"])}</td>
                <td class="py-2 text-right font-semibold">{_format_money(row["total_value"])}</td>
            </tr>
            """
            for row in rows
        )

        if not rows_html:
            rows_html = """
            <tr>
                <td colspan="4" class="py-4 text-center text-base-content/60">Nenhum serviço encontrado para esta OS.</td>
            </tr>
            """

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir serviços realizados</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Revise os serviços e finalize a emissão da NFS-e.</p>"),
                HTML(
                    f"""
                    <div class="overflow-x-auto mb-6">
                        <table class="table table-zebra">
                            <thead>
                                <tr>
                                    <th>Serviço</th>
                                    <th class="text-center">Qtd</th>
                                    <th class="text-right">Valor Unitário</th>
                                    <th class="text-right">Valor Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows_html}
                            </tbody>
                            <tfoot>
                                <tr>
                                    <th colspan="3" class="text-right">Total de Serviços</th>
                                    <th class="text-right">{total_services_formatted}</th>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                    """
                ),
                Div(
                    Field("tax_class", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("service_description", wrapper_class="col-span-12 lg:col-span-8"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                css_class="space-y-4",
            )
        )

    def clean_tax_class(self) -> str:
        tax_class = str(self.cleaned_data.get("tax_class") or "").strip()
        if self._valid_tax_class_refs and tax_class not in self._valid_tax_class_refs:
            raise forms.ValidationError("Selecione uma classe de imposto valida da lista.")
        return tax_class


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


class WebmaniaCompanyUpdateForm(forms.ModelForm):
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

    tipo_tributacao = forms.ChoiceField(required=False, choices=[("", "Selecione"), *WebmaniaCompanyTaxType.choices], widget=SelectInput(choices=[("", "Selecione"), *WebmaniaCompanyTaxType.choices]))
    regime_tributario = forms.ChoiceField(required=False, choices=WEBMANIA_REGIME_TRIBUTARIO_CHOICES, widget=SelectInput(choices=WEBMANIA_REGIME_TRIBUTARIO_CHOICES))
    unidade_empresa = forms.ChoiceField(required=False, choices=WEBMANIA_UNIDADE_EMPRESA_CHOICES, widget=SelectInput(choices=WEBMANIA_UNIDADE_EMPRESA_CHOICES))
    orientacao_danfe = forms.ChoiceField(required=False, choices=WEBMANIA_ORIENTACAO_DANFE_CHOICES, widget=SelectInput(choices=WEBMANIA_ORIENTACAO_DANFE_CHOICES))
    desativar_epec = forms.ChoiceField(required=False, choices=WEBMANIA_ENABLED_FLAG_CHOICES, widget=SelectInput(choices=WEBMANIA_ENABLED_FLAG_CHOICES))
    ocultar_total_etiqueta = forms.ChoiceField(required=False, choices=WEBMANIA_ENABLED_FLAG_CHOICES, widget=SelectInput(choices=WEBMANIA_ENABLED_FLAG_CHOICES))

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

        self._initial_model_values = {field_name: getattr(self.instance, field_name, "") for field_name in self.Meta.fields}
        self._initial_secret_values = {field_name: getattr(self.instance, field_name, "") for field_name in self.secret_fields}

        self.fields["email"].required = True

        for field_name in self.secret_fields:
            if field_name in self.fields:
                self.initial[field_name] = ""

        for field_name in self.nullable_boolean_fields:
            if getattr(self.instance, field_name, None) is None:
                self.initial[field_name] = False

        cancel_url = reverse("finance:webmania_company_detail", kwargs={"pk": self.instance.pk})

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
                HTML("<p class='col-span-12 text-sm font-semibold text-base-content/80'>NF-e</p>"),
                Field("nfe_serie", wrapper_class="col-span-12 lg:col-span-3"),
                Field("nfe_numero", wrapper_class="col-span-12 lg:col-span-3"),
                Field("nfe_numero_dev", wrapper_class="col-span-12 lg:col-span-3"),
                HTML("<div class='col-span-12 divider my-1'></div>"),
                HTML("<p class='col-span-12 text-sm font-semibold text-base-content/80'>NFC-e</p>"),
                Field("nfce_serie", wrapper_class="col-span-12 lg:col-span-3"),
                Field("nfce_numero", wrapper_class="col-span-12 lg:col-span-3"),
                Field("nfce_numero_dev", wrapper_class="col-span-12 lg:col-span-3"),
                Field("nfce_id_csc", wrapper_class="col-span-12 lg:col-span-6"),
                Field("nfce_codigo_csc", wrapper_class="col-span-12 lg:col-span-6"),
                Field("nfce_id_csc_dev", wrapper_class="col-span-12 lg:col-span-6"),
                Field("nfce_codigo_csc_dev", wrapper_class="col-span-12 lg:col-span-6"),
                HTML("<div class='col-span-12 divider my-1'></div>"),
                HTML("<p class='col-span-12 text-sm font-semibold text-base-content/80'>NFS-e</p>"),
                Field("nfse_rps_serie", wrapper_class="col-span-12 lg:col-span-3"),
                Field("nfse_rps_numero", wrapper_class="col-span-12 lg:col-span-3"),
                Field("nfse_lote_rps_numero", wrapper_class="col-span-12 lg:col-span-3"),
                Field("nfse_rps_numero_dev", wrapper_class="col-span-12 lg:col-span-3"),
                Field("cnae", wrapper_class="col-span-12 lg:col-span-3"),
                Field("regime_apuracao_sn", wrapper_class="col-span-12 lg:col-span-3"),
                Field("regime_especial_nacional", wrapper_class="col-span-12 lg:col-span-3"),
                Field("regime_especial_municipal", wrapper_class="col-span-12 lg:col-span-3"),
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

        cnpj = str(cleaned_data.get("cnpj") or "").strip()
        cpf = str(cleaned_data.get("cpf") or "").strip()
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

        if has_pj_data:
            if not cnpj:
                self.add_error("cnpj", "Ao informar Razão Social, o CNPJ é obrigatório.")
            if not razao_social:
                self.add_error("razao_social", "Ao informar CNPJ, a Razão Social é obrigatória.")
            return cleaned_data

        if not cpf:
            self.add_error("cpf", "Ao informar Nome Completo, o CPF é obrigatório.")
        if not nome_completo:
            self.add_error("nome_completo", "Ao informar CPF, o Nome Completo é obrigatório.")

        return cleaned_data

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

        return payload

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

        if commit:
            instance.save()

        return instance


NFE_SCENARIO_CHOICES = (
    ("", "Selecione"),
    ("saida_dentro_estado", "Saída dentro do estado"),
    ("saida_fora_estado", "Saída fora do estado"),
    ("saida_exterior", "Saída exterior"),
    ("entrada_dentro_estado", "Entrada dentro do estado"),
    ("entrada_fora_estado", "Entrada fora do estado"),
    ("entrada_exterior", "Entrada exterior"),
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


class TaxClassFormBase(forms.Form):
    referencia = forms.CharField(label="Referência", required=False, max_length=30, widget=TextInput())
    descricao = forms.CharField(label="Descrição", required=True, max_length=255, widget=TextInput())
    informacoes_fisco = forms.CharField(label="Informações ao Fisco", required=False, widget=TextareaInput(rows=3))
    informacoes_complementares = forms.CharField(label="Informações complementares", required=False, widget=TextareaInput(rows=3))
    base_payload_json = forms.CharField(required=False, widget=forms.HiddenInput())

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


class NfeTaxClassForm(TaxClassFormBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault("tipo_emissao", "1")
            self.initial.setdefault("tributacao_iss", "1")
            self.initial.setdefault("retencao_iss", "1")
            self.initial.setdefault("cst_pis_cofins", "00")
            self.initial.setdefault("retencao_pis_cofins", "0")

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
    codigo_servico = forms.CharField(label="Código do serviço", required=True, widget=TextInput())
    tipo_emissao = forms.ChoiceField(label="Tipo de emissão", required=True, choices=TIPO_EMISSAO_NFSE_CHOICES, widget=SelectInput(choices=TIPO_EMISSAO_NFSE_CHOICES))
    codigo_tributacao_municipio = forms.CharField(label="Código tributação município", required=False, widget=TextInput())
    tributacao_iss = forms.ChoiceField(label="Tributação ISS", required=True, choices=TRIBUTACAO_ISS_CHOICES, widget=SelectInput(choices=TRIBUTACAO_ISS_CHOICES))
    tipo_imunidade = forms.ChoiceField(label="Tipo imunidade", required=False, choices=TIPO_IMUNIDADE_CHOICES, widget=SelectInput(choices=TIPO_IMUNIDADE_CHOICES))
    retencao_iss = forms.ChoiceField(label="Retenção ISS", required=True, choices=RETENCAO_ISS_NACIONAL_CHOICES, widget=SelectInput(choices=RETENCAO_ISS_NACIONAL_CHOICES))
    cst_pis_cofins = forms.ChoiceField(label="CST PIS/COFINS", required=False, choices=CST_PIS_COFINS_CHOICES, widget=SelectInput(choices=CST_PIS_COFINS_CHOICES))
    retencao_pis_cofins = forms.ChoiceField(label="Retenção PIS/COFINS", required=False, choices=RETENCAO_PIS_COFINS_CHOICES, widget=SelectInput(choices=RETENCAO_PIS_COFINS_CHOICES))

    natureza_operacao = forms.ChoiceField(label="Natureza da operação (ABRASF)", required=False, choices=NATUREZA_OPERACAO_CHOICES, widget=SelectInput(choices=NATUREZA_OPERACAO_CHOICES))
    exigibilidade_iss = forms.ChoiceField(label="Exigibilidade ISS (ABRASF)", required=False, choices=EXIGIBILIDADE_ISS_CHOICES, widget=SelectInput(choices=EXIGIBILIDADE_ISS_CHOICES))
    iss_retido = forms.ChoiceField(label="ISS retido (ABRASF)", required=False, choices=ISS_RETIDO_CHOICES, widget=SelectInput(choices=ISS_RETIDO_CHOICES))
    responsavel_retencao = forms.ChoiceField(label="Responsável retenção", required=False, choices=RESPONSAVEL_RETENCAO_CHOICES, widget=SelectInput(choices=RESPONSAVEL_RETENCAO_CHOICES))
    codigo_cnae = forms.CharField(label="Código CNAE", required=False, widget=TextInput())

    iss = forms.DecimalField(label="Alíquota ISS", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    pis = forms.DecimalField(label="Alíquota PIS", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    cofins = forms.DecimalField(label="Alíquota COFINS", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    inss = forms.DecimalField(label="Alíquota INSS", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    ir = forms.DecimalField(label="Alíquota IR", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    csll = forms.DecimalField(label="Alíquota CSLL", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

    ibs_situacao_tributaria = forms.CharField(label="IBS/CBS Situação tributária", required=False, widget=TextInput())
    ibs_classificacao_tributaria = forms.CharField(label="IBS/CBS Classificação tributária", required=False, widget=TextInput())
    ibs_situacao_tributaria_regular = forms.CharField(label="IBS/CBS Situação regular", required=False, widget=TextInput())
    ibs_classificacao_tributaria_regular = forms.CharField(label="IBS/CBS Classificação regular", required=False, widget=TextInput())
    ibs_credito_presumido = forms.CharField(label="IBS/CBS Crédito presumido", required=False, widget=TextInput())
    ibs_aliquota_diferimento_estadual = forms.DecimalField(label="IBS estadual diferimento (%)", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    ibs_aliquota_diferimento_municipal = forms.DecimalField(label="IBS municipal diferimento (%)", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    cbs_aliquota_diferimento = forms.DecimalField(label="CBS diferimento (%)", required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

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
                initial[field_name] = str(payload.get(field_name))

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
                HTML("<h3 class='font-semibold mt-2'>Campos específicos de provedor (opcional)</h3>"),
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
                HTML("<h3 class='font-semibold mt-2'>IBS/CBS (Opcional)</h3>"),
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

        codigo_servico = str(cleaned_data.get("codigo_servico") or "")
        codigo_servico_digits = "".join(char for char in codigo_servico if char.isdigit())
        if len(codigo_servico_digits) != 6:
            self.add_error("codigo_servico", "Informe um código de serviço com 6 dígitos para o padrão nacional.")
        else:
            cleaned_data["codigo_servico"] = codigo_servico_digits

        codigo_tributacao = str(cleaned_data.get("codigo_tributacao_municipio") or "")
        codigo_tributacao_digits = "".join(char for char in codigo_tributacao if char.isdigit())
        if not codigo_tributacao_digits and len(codigo_servico_digits) == 6:
            cleaned_data["codigo_tributacao_municipio"] = codigo_servico_digits[:3]
        elif codigo_tributacao_digits:
            if len(codigo_tributacao_digits) != 3:
                self.add_error("codigo_tributacao_municipio", "Informe o código de tributação com 3 dígitos.")
            cleaned_data["codigo_tributacao_municipio"] = codigo_tributacao_digits

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

        payload.setdefault("cst_pis_cofins", "00")
        payload.setdefault("retencao_pis_cofins", "0")

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


class ScenarioFormBase(forms.Form):
    source_index = forms.IntegerField(required=False, widget=forms.HiddenInput())

    payload_fields: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    decimal_fields: dict[str, int] = {}

    @staticmethod
    def _validate_tipo_pessoa_by_cenario(form: "ScenarioFormBase", cleaned_data: dict[str, Any]) -> None:
        cenario = str(cleaned_data.get("cenario") or "")
        tipo_pessoa = str(cleaned_data.get("tipo_pessoa") or "")
        if not cenario or not tipo_pessoa:
            return

        if cenario == "saida_exterior" and tipo_pessoa != "estrangeira":
            form.add_error("tipo_pessoa", "Para cenário de saída exterior, o tipo de pessoa deve ser Estrangeira.")

        if cenario not in {"saida_exterior", "padrao"} and tipo_pessoa == "estrangeira":
            form.add_error("tipo_pessoa", "Tipo de pessoa estrangeira é válido apenas para cenário de saída exterior ou padrão.")

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
        if self._is_empty_row(cleaned_data):
            cleaned_data["_is_empty"] = True
            return cleaned_data

        for field_name in self.required_fields:
            if cleaned_data.get(field_name) in (None, ""):
                self.add_error(field_name, "Campo obrigatório para este cenário.")

        cleaned_data["_is_empty"] = False
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
    tipo_tributacao = forms.ChoiceField(required=False, choices=ICMS_TIPO_TRIBUTACAO_CHOICES, widget=SelectInput(choices=ICMS_TIPO_TRIBUTACAO_CHOICES))
    cenario = forms.ChoiceField(required=False, choices=NFE_SCENARIO_CHOICES, widget=SelectInput(choices=NFE_SCENARIO_CHOICES))
    tipo_pessoa = forms.ChoiceField(required=False, choices=TIPO_PESSOA_CHOICES, widget=SelectInput(choices=TIPO_PESSOA_CHOICES))
    nao_contribuinte = forms.BooleanField(required=False, widget=CheckboxInput())
    codigo_cfop = forms.CharField(required=False, max_length=10, widget=TextInput())
    situacao_tributaria = forms.CharField(required=False, max_length=3, widget=TextInput())
    aliquota_credito = forms.DecimalField(required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))
    aliquota_importacao = forms.DecimalField(required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

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
            self.add_error("aliquota_importacao", "Obrigatório para cenário de importação (entrada exterior).")

        if situacao_tributaria in {"101", "201"} and cleaned_data.get("aliquota_credito") in (None, ""):
            self.add_error("aliquota_credito", "Obrigatório para CST 101 ou 201.")

        if cleaned_data.get("nao_contribuinte") and tipo_pessoa != "juridica":
            self.add_error("nao_contribuinte", "Use esta opção apenas para destinatário pessoa jurídica.")

        if cenario == "saida_exterior" and tipo_pessoa != "estrangeira":
            self.add_error("tipo_pessoa", "Para cenário de saída exterior, o tipo de pessoa deve ser Estrangeira.")

        if cenario != "saida_exterior" and tipo_pessoa == "estrangeira":
            self.add_error("tipo_pessoa", "Tipo de pessoa estrangeira é válido apenas para cenário de saída exterior.")

        codigo_cfop = str(cleaned_data.get("codigo_cfop") or "")
        if codigo_cfop:
            digits = "".join(char for char in codigo_cfop if char.isdigit())
            if len(digits) != 4:
                self.add_error("codigo_cfop", "CFOP deve conter 4 dígitos.")

        return cleaned_data


class IpiScenarioForm(ScenarioFormBase):
    cenario = forms.ChoiceField(required=False, choices=SCENARIO_PADRAO_CHOICES, widget=SelectInput(choices=SCENARIO_PADRAO_CHOICES))
    tipo_pessoa = forms.ChoiceField(required=False, choices=TIPO_PESSOA_CHOICES, widget=SelectInput(choices=TIPO_PESSOA_CHOICES))
    situacao_tributaria = forms.CharField(required=False, max_length=3, widget=TextInput())
    codigo_enquadramento = forms.CharField(required=False, max_length=3, widget=TextInput())
    aliquota = forms.DecimalField(required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

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
    cenario = forms.ChoiceField(required=False, choices=SCENARIO_PADRAO_CHOICES, widget=SelectInput(choices=SCENARIO_PADRAO_CHOICES))
    tipo_pessoa = forms.ChoiceField(required=False, choices=TIPO_PESSOA_CHOICES, widget=SelectInput(choices=TIPO_PESSOA_CHOICES))
    situacao_tributaria = forms.CharField(required=False, max_length=3, widget=TextInput())
    aliquota = forms.DecimalField(required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

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
    cenario = forms.ChoiceField(required=False, choices=SCENARIO_PADRAO_CHOICES, widget=SelectInput(choices=SCENARIO_PADRAO_CHOICES))
    tipo_pessoa = forms.ChoiceField(required=False, choices=TIPO_PESSOA_CHOICES, widget=SelectInput(choices=TIPO_PESSOA_CHOICES))
    situacao_tributaria = forms.CharField(required=False, max_length=3, widget=TextInput())
    aliquota = forms.DecimalField(required=False, max_digits=7, decimal_places=2, widget=DecimalInput(decimal_places=2))

    payload_fields = ("cenario", "tipo_pessoa", "situacao_tributaria", "aliquota")
    required_fields = ("cenario", "tipo_pessoa", "situacao_tributaria", "aliquota")
    decimal_fields = {"aliquota": 2}

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        if cleaned_data.get("_is_empty"):
            return cleaned_data

        self._validate_tipo_pessoa_by_cenario(self, cleaned_data)
        return cleaned_data


IcmsScenarioFormSet = formset_factory(IcmsScenarioForm, extra=1, can_delete=True)
IpiScenarioFormSet = formset_factory(IpiScenarioForm, extra=1, can_delete=True)
PisScenarioFormSet = formset_factory(PisScenarioForm, extra=1, can_delete=True)
CofinsScenarioFormSet = formset_factory(CofinsScenarioForm, extra=1, can_delete=True)
