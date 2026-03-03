from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms

from apps.core.widgets import SelectInput, TextInput, TextareaInput
from apps.finance.models import NfseRequest
from apps.finance.services.pricing import build_slider_allocation_for_workorder
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

    total_services = build_slider_allocation_for_workorder(workorder=workorder).services_target
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
