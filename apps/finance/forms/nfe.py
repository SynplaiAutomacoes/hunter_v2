from __future__ import annotations

from html import escape
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms

from apps.core.widgets import SelectInput
from apps.finance.forms.emission_ui import (
    build_slider_widget_attrs,
    build_step5_pricing_panel_data,
    build_step5_pricing_panel_layout,
    build_step5_preview_oob_html,
    format_money,
    resolve_initial_slider,
)
from apps.finance.forms.request_steps_shared import SharedEmissionCustomerReviewForm, SharedEmissionWorkorderSelectionForm
from apps.finance.models.finance import NfeRequest
from apps.finance.services.nfe_emission import NfeEmissionError, build_nfe_preview_rows


class NfeRequestStep1Form(SharedEmissionWorkorderSelectionForm):
    step_subtitle = "Selecione a ordem de servico aprovada que sera utilizada para emitir a NF-e."

    class Meta:
        model = NfeRequest
        fields = ["workorder"]


class NfeRequestStep2Form(SharedEmissionCustomerReviewForm):
    class Meta:
        model = NfeRequest
        fields: list[str] = []


class NfeRequestStep3Form(forms.ModelForm):
    class Meta:
        model = NfeRequest
        fields = ["pricing_slider", "tax_class"]

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
        slider_field.help_text = "Ajuste a distribuicao da margem para esta NF-e sem alterar o orcamento."
        slider_field.widget = forms.NumberInput(
            attrs=build_slider_widget_attrs(
                preview_url=f"{preview_url}&preview=1" if preview_url else "",
                include_selector="#nfe-form",
                target_selector="#nfe-preview-block",
                swap="none",
                trigger="input changed delay:120ms, change",
                sync_selector="#nfe-form:abort",
            )
        )

        tax_class_field = self.fields["tax_class"]
        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(self.tax_class_choices)
        tax_class_field.widget = SelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe de imposto de produto (NF-e)."
        self._valid_tax_class_refs = {value for value, _ in self.tax_class_choices if value}

        current_tax_class_source = self.data.get("tax_class") if self.is_bound else self.initial.get("tax_class", getattr(self.instance, "tax_class", ""))
        current_tax_class = str(current_tax_class_source or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs:
            self.initial["tax_class"] = next(iter(self._valid_tax_class_refs))

        rows: list[dict[str, Any]] = []
        total_products_formatted = format_money(0)
        total_services_formatted = format_money(0)
        warning_html = ""
        panel_data = None

        if self.instance and self.instance.workorder_id:
            panel_data = build_step5_pricing_panel_data(workorder=self.instance.workorder, selected_slider=selected_slider)
            try:
                rows, allocation = build_nfe_preview_rows(
                    workorder=self.instance.workorder,
                    persisted_slider=getattr(self.instance, "pricing_slider", None),
                    slider_override=selected_slider,
                )
                total_products_formatted = format_money(allocation.products_target)
                total_services_formatted = format_money(allocation.services_target)
            except NfeEmissionError as exc:
                warning_html = f"<div class='alert alert-warning mb-4'>{escape(str(exc))}</div>"

        rows_html = "".join(
            f"""
            <tr class="border-b border-base-300/60">
                <td class="py-2">{escape(str(row["description"]))}</td>
                <td class="py-2 text-center">{row["quantity"]}</td>
                <td class="py-2 text-right">{format_money(row["base_total"])}</td>
                <td class="py-2 text-right font-semibold">{format_money(row["target_total"])}</td>
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

        preview_html = f"""
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

        self.preview_warning_html = warning_html
        self.preview_html = preview_html
        self.preview_panel_html = (
            build_step5_preview_oob_html(prefix="nfe", panel_data=panel_data, warning_html=warning_html, preview_html=preview_html) if panel_data is not None else f'<div id="nfe-warning-block" hx-swap-oob="true">{warning_html}</div><div id="nfe-preview-block" hx-swap-oob="true">{preview_html}</div>'
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir produtos e impostos</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Revise os produtos da OS e finalize a emissao da NF-e.</p>"),
                build_step5_pricing_panel_layout(prefix="nfe", panel_data=panel_data, slider_field_name="pricing_slider", form_selector="#nfe-form") if panel_data is not None else HTML(""),
                Div(
                    Field("tax_class", wrapper_class="col-span-12 lg:col-span-6"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                HTML('<div id="nfe-warning-block">' + warning_html + "</div>"),
                HTML('<div id="nfe-preview-block">' + preview_html + "</div>"),
                css_class="space-y-4",
            )
        )

    def clean_tax_class(self) -> str:
        tax_class = str(self.cleaned_data.get("tax_class") or "").strip()
        if self._valid_tax_class_refs and tax_class not in self._valid_tax_class_refs:
            raise forms.ValidationError("Selecione uma classe de imposto valida da lista.")
        return tax_class
