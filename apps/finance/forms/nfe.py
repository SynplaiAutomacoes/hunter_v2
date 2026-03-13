from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms

from apps.core.widgets import SelectInput
from apps.finance.models.finance import NfeRequest
from apps.finance.services.nfe_emission import NfeEmissionError, build_nfe_preview_rows
from apps.workorder.models import WorkOrder, WorkOrderStatus


def _format_money(value: Any) -> str:
    amount: Decimal
    if hasattr(value, "amount"):
        amount = value.amount
    else:
        amount = Decimal(str(value or 0))
    return f"R$ {amount:.2f}".replace(".", ",")


class NfeRequestStep1Form(forms.ModelForm):
    class Meta:
        model = NfeRequest
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
            customer_name = customer.name if customer else "Cliente nao informado"
            return f"Ordem de Servico - {customer_name} - #{workorder.pk}"

        field.label_from_instance = _label_from_instance
        field.widget = SelectInput(choices=field.choices)
        field.label = "Ordem de Servico"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Selecionar Ordem de Servico</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Selecione a ordem de servico aprovada que sera utilizada para emitir a NF-e.</p>"),
                Field("workorder"),
                css_class="space-y-4",
            )
        )


class NfeRequestStep2Form(forms.ModelForm):
    class Meta:
        model = NfeRequest
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

        customer_name = escape(customer.name) if customer else "Nao informado"
        customer_doc = escape(customer.cpf_or_cnpj_formatted) if customer else "Nao informado"
        customer_phone = escape(str(customer.phone)) if customer and customer.phone else "Nao informado"
        customer_email = escape(customer.email) if customer and customer.email else "Nao informado"
        customer_address = escape(customer.full_address) if customer else "Nao informado"
        vehicle_label = escape(str(vehicle)) if vehicle else "Nao informado"

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir dados do cliente</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Valide os dados do cliente antes de avancar para a etapa de emissao.</p>"),
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
                            <p class="text-xs uppercase text-base-content/60">Endereco</p>
                            <p class="font-semibold">{customer_address}</p>
                        </div>
                        <div class="md:col-span-2">
                            <p class="text-xs uppercase text-base-content/60">Veiculo</p>
                            <p class="font-semibold">{vehicle_label}</p>
                        </div>
                    </div>
                    """
                ),
                css_class="space-y-4",
            )
        )


class NfeRequestStep3Form(forms.ModelForm):
    class Meta:
        model = NfeRequest
        fields = ["tax_class"]

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.tax_class_choices = kwargs.pop("tax_class_choices", [])
        super().__init__(*args, **kwargs)

        tax_class_field = self.fields["tax_class"]
        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(self.tax_class_choices)
        tax_class_field.widget = SelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe de imposto de produto (NF-e)."
        self._valid_tax_class_refs = {value for value, _ in self.tax_class_choices if value}

        current_tax_class = str(getattr(self.instance, "tax_class", "") or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs:
            self.initial["tax_class"] = next(iter(self._valid_tax_class_refs))

        rows: list[dict[str, Any]] = []
        total_products_formatted = _format_money(Decimal("0"))
        total_services_formatted = _format_money(Decimal("0"))
        slider_display = "0"
        warning_html = ""

        if self.instance and self.instance.workorder_id:
            try:
                rows, allocation = build_nfe_preview_rows(workorder=self.instance.workorder)
                total_products_formatted = _format_money(allocation.products_target)
                total_services_formatted = _format_money(allocation.services_target)
                slider_display = str(allocation.slider)
            except NfeEmissionError as exc:
                warning_html = f"<div class='alert alert-warning mb-4'>{escape(str(exc))}</div>"

        rows_html = "".join(
            f"""
            <tr class="border-b border-base-300/60">
                <td class="py-2">{escape(str(row["description"]))}</td>
                <td class="py-2 text-center">{row["quantity"]}</td>
                <td class="py-2 text-right">{_format_money(row["base_total"])}</td>
                <td class="py-2 text-right font-semibold">{_format_money(row["target_total"])}</td>
            </tr>
            """
            for row in rows
        )

        if not rows_html:
            rows_html = """
            <tr>
                <td colspan="4" class="py-4 text-center text-base-content/60">Nenhuma peca elegivel encontrada para esta OS.</td>
            </tr>
            """

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir produtos e impostos</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Revise os produtos da OS e finalize a emissao da NF-e.</p>"),
                HTML(warning_html),
                HTML(
                    f"""
                    <div class="overflow-x-auto mb-6">
                        <table class="table table-zebra">
                            <thead>
                                <tr>
                                    <th>Produto</th>
                                    <th class="text-center">Qtd</th>
                                    <th class="text-right">Total Base</th>
                                    <th class="text-right">Total para NF-e</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows_html}
                            </tbody>
                            <tfoot>
                                <tr>
                                    <th colspan="3" class="text-right">Slider do Orcamento</th>
                                    <th class="text-right">{slider_display}</th>
                                </tr>
                                <tr>
                                    <th colspan="3" class="text-right">Total NF-e (produtos)</th>
                                    <th class="text-right">{total_products_formatted}</th>
                                </tr>
                                <tr>
                                    <th colspan="3" class="text-right">Saldo NFS-e (servicos)</th>
                                    <th class="text-right">{total_services_formatted}</th>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                    """
                ),
                Div(
                    Field("tax_class", wrapper_class="col-span-12 lg:col-span-5"),
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
