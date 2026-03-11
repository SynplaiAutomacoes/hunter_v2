from __future__ import annotations

from html import escape
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms

from apps.core.widgets import SelectInput, TextInput, TextareaInput
from apps.finance.forms.emission_ui import (
    build_slider_widget_attrs,
    build_step5_pricing_panel_data,
    build_step5_pricing_panel_layout,
    build_step5_preview_oob_html,
    format_money,
    resolve_initial_slider,
)
from apps.finance.forms.request_steps_shared import SharedEmissionCustomerReviewForm, SharedEmissionWorkorderSelectionForm
from apps.finance.models.finance import NfseRequest
from apps.finance.services.pricing import build_nfse_service_preview_rows, build_slider_allocation_for_workorder
from apps.workorder.models import WorkOrder


def _collect_service_rows(
    workorder: WorkOrder,
    *,
    persisted_slider: int | None = None,
    slider_override: int | None = None,
) -> tuple[list[dict[str, Any]], str, str]:
    rows = build_nfse_service_preview_rows(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    )

    total_services = build_slider_allocation_for_workorder(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    ).services_target
    total_services_formatted = format_money(total_services)

    if rows:
        default_description = "; ".join(f"{row['quantity']}x {row['description']}" for row in rows)
    else:
        default_description = f"Prestação de serviço referente à OS #{workorder.pk}"

    return rows, total_services_formatted, default_description


class NfseRequestStep1Form(SharedEmissionWorkorderSelectionForm):
    step_title = "Selecionar Ordem de Serviço"
    step_subtitle = "Selecione a ordem de serviço aprovada que será utilizada para emitir a NFS-e."
    workorder_label = "Ordem de Serviço"
    empty_customer_label = "Cliente não informado"

    class Meta:
        model = NfseRequest
        fields = ["workorder"]


class NfseRequestStep2Form(SharedEmissionCustomerReviewForm):
    step_subtitle = "Valide os dados do cliente antes de avançar para a etapa de emissão."
    empty_value_label = "Não informado"
    address_label = "Endereço"
    vehicle_label = "Veículo"

    class Meta:
        model = NfseRequest
        fields: list[str] = []


class NfseRequestStep3Form(forms.ModelForm):
    class Meta:
        model = NfseRequest
        fields = ["pricing_slider", "tax_class", "service_description"]
        widgets = {
            "tax_class": TextInput(),
            "service_description": TextareaInput(rows=4),
        }

    def __init__(self, *args, **kwargs):
        self.workshop = kwargs.pop("workshop", None)
        self.request = kwargs.pop("request", None)
        self.tax_class_choices = kwargs.pop("tax_class_choices", [])
        super().__init__(*args, **kwargs)

        preview_url = f"{self.request.path}?step=3" if self.request is not None else ""
        default_slider = int(getattr(getattr(getattr(self.instance, "workorder", None), "budget", None), "slider", 0) or 0)
        persisted_slider = getattr(self.instance, "pricing_slider", None)
        selected_slider = resolve_initial_slider(
            initial_value=self.data.get("pricing_slider") if self.is_bound else self.initial.get("pricing_slider"),
            persisted_slider=persisted_slider,
            default_slider=default_slider,
        )

        slider_field = self.fields["pricing_slider"]
        slider_field.label = "Slider da emissao"
        slider_field.help_text = "Ajuste a distribuicao da margem para esta NFS-e sem alterar o orcamento."
        slider_field.widget = forms.NumberInput(
            attrs=build_slider_widget_attrs(
                preview_url=f"{preview_url}&preview=1" if preview_url else "",
                include_selector="#nfse-form",
                target_selector="#nfse-preview-block",
                swap="none",
                trigger="input changed delay:120ms, change",
                sync_selector="#nfse-form:abort",
            )
        )

        tax_class_field = self.fields["tax_class"]
        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(self.tax_class_choices)
        tax_class_field.widget = SelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe de imposto de servico (NFS-e)."
        self._valid_tax_class_refs = {value for value, _ in self.tax_class_choices if value}

        current_tax_class_source = self.data.get("tax_class") if self.is_bound else self.initial.get("tax_class", getattr(self.instance, "tax_class", ""))
        current_tax_class = str(current_tax_class_source or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs:
            default_tax_class = next(iter(self._valid_tax_class_refs))
            self.initial["tax_class"] = default_tax_class

        rows: list[dict[str, Any]] = []
        total_services_formatted = format_money(0)
        default_description = "Prestação de serviço"
        warning_html = ""
        panel_data = None

        if self.instance and self.instance.workorder_id:
            panel_data = build_step5_pricing_panel_data(workorder=self.instance.workorder, selected_slider=selected_slider)
            rows, total_services_formatted, default_description = _collect_service_rows(
                self.instance.workorder,
                persisted_slider=getattr(self.instance, "pricing_slider", None),
                slider_override=selected_slider,
            )
            allocation = build_slider_allocation_for_workorder(
                workorder=self.instance.workorder,
                persisted_slider=getattr(self.instance, "pricing_slider", None),
                slider_override=selected_slider,
            )
            if allocation.services_target <= 0:
                warning_html = "<div class='alert alert-warning mb-4'>A configuracao atual do slider nao deixa saldo de servicos para emitir NFS-e.</div>"

        if not self.instance.service_description and "service_description" not in self.initial:
            self.initial["service_description"] = default_description

        rows_html = "".join(
            f"""
            <tr class="border-b border-base-300/60">
                <td class="py-2">{escape(str(row["description"]))}</td>
                <td class="py-2 text-center">{row["quantity"]}</td>
                <td class="py-2 text-right">{format_money(row["unit_value"])}</td>
                <td class="py-2 text-right font-semibold">{format_money(row["total_value"])}</td>
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

        preview_html = f"""
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

        self.preview_warning_html = warning_html
        self.preview_html = preview_html
        self.preview_panel_html = (
            build_step5_preview_oob_html(prefix="nfse", panel_data=panel_data, warning_html=warning_html, preview_html=preview_html) if panel_data is not None else f'<div id="nfse-warning-block" hx-swap-oob="true">{warning_html}</div><div id="nfse-preview-block" hx-swap-oob="true">{preview_html}</div>'
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir serviços realizados</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Revise os serviços e finalize a emissão da NFS-e.</p>"),
                build_step5_pricing_panel_layout(prefix="nfse", panel_data=panel_data, slider_field_name="pricing_slider", form_selector="#nfse-form") if panel_data is not None else HTML(""),
                Div(
                    Field("tax_class", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("service_description", wrapper_class="col-span-12 lg:col-span-8"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                HTML('<div id="nfse-warning-block">' + warning_html + "</div>"),
                HTML('<div id="nfse-preview-block">' + preview_html + "</div>"),
                css_class="space-y-4",
            )
        )

    def clean_tax_class(self) -> str:
        tax_class = str(self.cleaned_data.get("tax_class") or "").strip()
        if self._valid_tax_class_refs and tax_class not in self._valid_tax_class_refs:
            raise forms.ValidationError("Selecione uma classe de imposto valida da lista.")
        return tax_class
