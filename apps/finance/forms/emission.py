from __future__ import annotations

from html import escape
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms
from django.urls import reverse

from apps.core.widgets import SelectInput, TextareaInput
from apps.finance.forms.emission_ui import (
    build_slider_widget_attrs,
    build_step5_pricing_panel_data,
    build_step5_preview_oob_html,
    build_step5_summary_layout,
    clamp_slider_value,
    format_money,
)
from apps.finance.services.emission import build_default_service_description_for_workorder
from apps.finance.services.nfe_emission import NfeEmissionError, build_nfe_preview_rows
from apps.finance.services.pricing import build_emission_pricing_snapshot_for_workorder, build_nfse_service_preview_rows, build_slider_allocation_for_workorder
from apps.workorder.models import WorkOrder, WorkOrderStatus


EMISSION_NOTE_TYPE_CHOICES: list[tuple[str, str]] = [("nfe", "NF-e"), ("nfse", "NFS-e")]
EMISSION_NOTE_MODE_CHOICES: list[tuple[str, str]] = [("nfe", "NF-e"), ("nfse", "NFS-e"), ("both", "Ambas")]


def _resolve_note_mode(value: object) -> str:
    note_mode = str(value or "").strip().lower()
    if note_mode in {"nfe", "nfse", "both"}:
        return note_mode
    return "nfe"


def _build_summary_warning_html(*, workorder: WorkOrder, selected_slider: int) -> str:
    allocation = build_slider_allocation_for_workorder(workorder=workorder, slider_override=selected_slider)
    warnings: list[str] = []

    if allocation.products_target <= 0:
        warnings.append("Com a configuracao atual do slider, nao ha saldo de produtos para emitir NF-e.")
    if allocation.services_target <= 0:
        warnings.append("Com a configuracao atual do slider, nao ha saldo de servicos para emitir NFS-e.")

    return "".join(f"<div class='alert alert-warning'>{warning}</div>" for warning in warnings)


def _build_summary_preview_html(*, workorder: WorkOrder, selected_slider: int) -> str:
    snapshot = build_emission_pricing_snapshot_for_workorder(workorder=workorder, slider_override=selected_slider)
    product_rows_html = "".join(
        f"""
        <tr class="border-b border-base-300/60">
            <td class="py-2">{escape(str(line.description))}</td>
            <td class="py-2 text-center">{line.quantity}</td>
            <td class="py-2 text-right">{format_money(line.adjusted_unit_price)}</td>
            <td class="py-2 text-right font-semibold">{format_money(line.total_price)}</td>
        </tr>
        """
        for line in snapshot.product_lines
    )
    service_rows_html = "".join(
        f"""
        <tr class="border-b border-base-300/60">
            <td class="py-2">{escape(str(line.description))}</td>
            <td class="py-2 text-center">{line.quantity}</td>
            <td class="py-2 text-right">{format_money(line.adjusted_unit_price)}</td>
            <td class="py-2 text-right font-semibold">{format_money(line.total_price)}</td>
        </tr>
        """
        for line in snapshot.service_lines
    )

    if not product_rows_html:
        product_rows_html = """
        <tr>
            <td colspan="4" class="py-4 text-center text-base-content/60">Nenhum produto encontrado nesta OS.</td>
        </tr>
        """

    if not service_rows_html:
        service_rows_html = """
        <tr>
            <td colspan="4" class="py-4 text-center text-base-content/60">Nenhum servico encontrado nesta OS.</td>
        </tr>
        """

    return f"""
        <div class="rounded-2xl border border-base-300 bg-base-100 p-5 shadow-sm">
            <div class="mb-4 flex items-center justify-between gap-3 flex-wrap">
                <div>
                    <h3 class="text-xl font-bold text-base-content">Itens consolidados da emissao</h3>
                    <p class="text-sm text-base-content/70">Os valores abaixo refletem o slider aplicado no resumo.</p>
                </div>
            </div>
            <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div class="rounded-xl border border-base-300 bg-base-100 p-4">
                    <h4 class="mb-3 text-lg font-bold text-base-content">Produtos</h4>
                    <div class="overflow-x-auto">
                        <table class="table table-zebra">
                            <thead>
                                <tr>
                                    <th>Descricao</th>
                                    <th class="text-center">Qtd</th>
                                    <th class="text-right">Valor Unitario</th>
                                    <th class="text-right">Valor Total</th>
                                </tr>
                            </thead>
                            <tbody>{product_rows_html}</tbody>
                        </table>
                    </div>
                </div>
                <div class="rounded-xl border border-base-300 bg-base-100 p-4">
                    <h4 class="mb-3 text-lg font-bold text-base-content">Servicos</h4>
                    <div class="overflow-x-auto">
                        <table class="table table-zebra">
                            <thead>
                                <tr>
                                    <th>Descricao</th>
                                    <th class="text-center">Qtd</th>
                                    <th class="text-right">Valor Unitario</th>
                                    <th class="text-right">Valor Total</th>
                                </tr>
                            </thead>
                            <tbody>{service_rows_html}</tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    """


def _build_nfe_preview_html(*, workorder: WorkOrder, selected_slider: int) -> tuple[str, str]:
    warning_html = ""
    total_products_formatted = format_money(0)
    total_services_formatted = format_money(0)
    rows: list[dict[str, Any]] = []

    try:
        rows, allocation = build_nfe_preview_rows(workorder=workorder, slider_override=selected_slider)
        total_products_formatted = format_money(allocation.products_target)
        total_services_formatted = format_money(allocation.services_target)
        if allocation.products_target <= 0:
            warning_html = "<div class='alert alert-warning'>A configuracao atual do slider nao deixa saldo de produtos para emitir NF-e.</div>"
    except NfeEmissionError as exc:
        warning_html = f"<div class='alert alert-warning'>{escape(str(exc))}</div>"

    rows_html = "".join(
        f"""
        <tr class="border-b border-base-300/60">
            <td class="py-2">{escape(str(row["description"]))}</td>
            <td class="py-2">{escape(str(row.get("ncm") or "-"))}</td>
            <td class="py-2 text-center">{row["quantity"]}</td>
            <td class="py-2 text-right">{format_money(row.get("target_unit_value", 0))}</td>
            <td class="py-2 text-right font-semibold">{format_money(row["target_total"])}</td>
        </tr>
        """
        for row in rows
    )

    if not rows_html:
        rows_html = """
        <tr>
            <td colspan="5" class="py-4 text-center text-base-content/60">Nenhum produto elegivel encontrado para esta OS.</td>
        </tr>
        """

    preview_html = f"""
        <div class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="rounded-xl border border-base-300 bg-base-200/50 p-4">
                    <p class="text-xs uppercase tracking-wide text-base-content/60">Total NF-e</p>
                    <p class="text-2xl font-black text-base-content">{total_products_formatted}</p>
                </div>
                <div class="rounded-xl border border-base-300 bg-base-200/50 p-4">
                    <p class="text-xs uppercase tracking-wide text-base-content/60">Saldo NFS-e</p>
                    <p class="text-2xl font-black text-base-content">{total_services_formatted}</p>
                </div>
            </div>
            <div class="overflow-x-auto rounded-2xl border border-base-300 bg-base-100 p-4 shadow-sm">
                <table class="table table-zebra">
                    <thead>
                        <tr>
                            <th>Produto</th>
                            <th>NCM</th>
                            <th class="text-center">Qtd</th>
                            <th class="text-right">Valor Unitario</th>
                            <th class="text-right">Valor Total</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
        </div>
    """
    return warning_html, preview_html


def _build_nfse_preview_html(*, workorder: WorkOrder, selected_slider: int) -> tuple[str, str]:
    allocation = build_slider_allocation_for_workorder(workorder=workorder, slider_override=selected_slider)
    warning_html = ""
    if allocation.services_target <= 0:
        warning_html = "<div class='alert alert-warning'>A configuracao atual do slider nao deixa saldo de servicos para emitir NFS-e.</div>"

    rows = build_nfse_service_preview_rows(workorder=workorder, slider_override=selected_slider)
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
            <td colspan="4" class="py-4 text-center text-base-content/60">Nenhum servico elegivel encontrado para esta OS.</td>
        </tr>
        """

    preview_html = f"""
        <div class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="rounded-xl border border-base-300 bg-base-200/50 p-4">
                    <p class="text-xs uppercase tracking-wide text-base-content/60">Total NFS-e</p>
                    <p class="text-2xl font-black text-base-content">{format_money(allocation.services_target)}</p>
                </div>
                <div class="rounded-xl border border-base-300 bg-base-200/50 p-4">
                    <p class="text-xs uppercase tracking-wide text-base-content/60">Saldo NF-e</p>
                    <p class="text-2xl font-black text-base-content">{format_money(allocation.products_target)}</p>
                </div>
            </div>
            <div class="overflow-x-auto rounded-2xl border border-base-300 bg-base-100 p-4 shadow-sm">
                <table class="table table-zebra">
                    <thead>
                        <tr>
                            <th>Servico</th>
                            <th class="text-center">Qtd</th>
                            <th class="text-right">Valor Unitario</th>
                            <th class="text-right">Valor Total</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
        </div>
    """
    return warning_html, preview_html


class EmissionStep1Form(forms.Form):
    workorder = forms.ModelChoiceField(queryset=WorkOrder.objects.none(), label="Ordem de Servico")

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)

        queryset = WorkOrder.objects.none()
        if workshop is not None:
            queryset = WorkOrder.objects.filter(workshop=workshop, status=WorkOrderStatus.APPROVED).select_related(
                "budget",
                "budget__customer",
                "budget__vehicle",
            )

        field = self.fields["workorder"]
        field.queryset = queryset.order_by("-id")

        def _label_from_instance(workorder: WorkOrder) -> str:
            customer = getattr(getattr(workorder, "budget", None), "customer", None)
            customer_name = customer.name if customer else "Cliente nao informado"
            return f"Ordem de Servico - {customer_name} - #{workorder.pk}"

        field.label_from_instance = _label_from_instance
        field.widget = SelectInput(choices=list(field.choices))

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Selecionar Ordem de Servico</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Selecione a OS aprovada que sera usada na emissao fiscal.</p>"),
                Field("workorder"),
                css_class="space-y-4",
            )
        )


class EmissionStep2Form(forms.Form):
    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)

        customer = None
        vehicle = None
        if workorder is not None:
            budget = workorder.budget
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
                HTML("<h2 class='text-2xl font-bold'>Conferir cliente</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Revise os dados do cliente e do veiculo antes de seguir.</p>"),
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


class EmissionStep3Form(forms.Form):
    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)

        products_html = ""
        services_html = ""
        total_products = format_money(0)
        total_services = format_money(0)

        if workorder is not None:
            snapshot = build_emission_pricing_snapshot_for_workorder(workorder=workorder)
            total_products = format_money(snapshot.total_products_value)
            total_services = format_money(snapshot.total_services_value)

            products_html = "".join(
                f"""
                <tr class="border-b border-base-300/60">
                    <td class="py-2">{escape(str(line.description))}</td>
                    <td class="py-2 text-center">{line.quantity}</td>
                    <td class="py-2 text-right">{format_money(line.raw_total)}</td>
                </tr>
                """
                for line in snapshot.product_lines
            )
            services_html = "".join(
                f"""
                <tr class="border-b border-base-300/60">
                    <td class="py-2">{escape(str(line.description))}</td>
                    <td class="py-2 text-center">{line.quantity}</td>
                    <td class="py-2 text-right">{format_money(line.raw_total)}</td>
                </tr>
                """
                for line in snapshot.service_lines
            )

        if not products_html:
            products_html = """
            <tr>
                <td colspan="3" class="py-4 text-center text-base-content/60">Nenhum produto encontrado nesta OS.</td>
            </tr>
            """

        if not services_html:
            services_html = """
            <tr>
                <td colspan="3" class="py-4 text-center text-base-content/60">Nenhum servico encontrado nesta OS.</td>
            </tr>
            """

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir produtos e servicos</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Revise os itens consolidados da OS antes de definir o tipo da nota.</p>"),
                HTML(
                    f"""
                    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
                        <div class="overflow-x-auto">
                            <h3 class="font-semibold mb-3">Produtos</h3>
                            <table class="table table-zebra">
                                <thead>
                                    <tr>
                                        <th>Descricao</th>
                                        <th class="text-center">Qtd</th>
                                        <th class="text-right">Total Base</th>
                                    </tr>
                                </thead>
                                <tbody>{products_html}</tbody>
                                <tfoot>
                                    <tr>
                                        <th colspan="2" class="text-right">Total Produtos</th>
                                        <th class="text-right">{total_products}</th>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>
                        <div class="overflow-x-auto">
                            <h3 class="font-semibold mb-3">Servicos</h3>
                            <table class="table table-zebra">
                                <thead>
                                    <tr>
                                        <th>Descricao</th>
                                        <th class="text-center">Qtd</th>
                                        <th class="text-right">Total Base</th>
                                    </tr>
                                </thead>
                                <tbody>{services_html}</tbody>
                                <tfoot>
                                    <tr>
                                        <th colspan="2" class="text-right">Total Servicos</th>
                                        <th class="text-right">{total_services}</th>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>
                    </div>
                    """
                ),
                css_class="space-y-4",
            )
        )


class EmissionStep4Form(forms.Form):
    pricing_slider = forms.IntegerField(label="Slider da emissao", min_value=-100, max_value=100)

    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)

        initial_slider = self.initial.get("pricing_slider", getattr(getattr(workorder, "budget", None), "slider", 0))
        selected_slider = clamp_slider_value(self.data.get("pricing_slider") if self.is_bound else initial_slider, default=int(initial_slider or 0))

        slider_field = self.fields["pricing_slider"]
        slider_field.widget = forms.NumberInput(
            attrs=build_slider_widget_attrs(
                preview_url=f"{reverse('finance:emission_create')}?step=4&preview=1",
                include_selector="#emission-form",
                target_selector="#emission-preview-block",
                swap="none",
                sync_selector="#emission-form:abort",
            )
        )
        slider_field.help_text = "Deslize para redistribuir a margem entre produtos e servicos antes de emitir as notas."

        warning_html = ""
        preview_html = ""
        panel_data = None
        if workorder is not None:
            panel_data = build_step5_pricing_panel_data(workorder=workorder, selected_slider=selected_slider)
            warning_html = _build_summary_warning_html(workorder=workorder, selected_slider=selected_slider)
            preview_html = _build_summary_preview_html(workorder=workorder, selected_slider=selected_slider)

        self.preview_warning_html = warning_html
        self.preview_html = preview_html
        self.preview_panel_html = (
            build_step5_preview_oob_html(prefix="emission", panel_data=panel_data, warning_html=warning_html, preview_html=preview_html) if panel_data is not None else f'<div id="emission-warning-block" hx-swap-oob="true">{warning_html}</div><div id="emission-preview-block" hx-swap-oob="true">{preview_html}</div>'
        )

        body_html = f"""
            <div class="space-y-4">
                <div id="emission-warning-block" class="space-y-3">{warning_html}</div>
                <div id="emission-preview-block">{preview_html}</div>
            </div>
        """

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Resumo</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Ajuste o slider e revise todos os produtos e servicos com os valores finais da emissao.</p>"),
                build_step5_summary_layout(prefix="emission", panel_data=panel_data, slider_field_name="pricing_slider", form_selector="#emission-form", body_html=body_html) if panel_data is not None else HTML(""),
                css_class="space-y-4",
            )
        )

    def clean_pricing_slider(self) -> int:
        return clamp_slider_value(self.cleaned_data.get("pricing_slider"), default=0)


class EmissionStep5Form(forms.Form):
    note_mode = forms.ChoiceField(label="Tipo de notas fiscais", choices=EMISSION_NOTE_MODE_CHOICES)

    def __init__(self, *args, **kwargs):
        note_mode_choices = kwargs.pop("note_mode_choices", EMISSION_NOTE_MODE_CHOICES)
        super().__init__(*args, **kwargs)

        note_mode_field = self.fields["note_mode"]
        note_mode_field.choices = list(note_mode_choices)
        note_mode_field.widget = SelectInput(choices=list(note_mode_choices))
        note_mode_field.help_text = "Escolha se a emissao sera somente de produtos, somente de servicos, ou das duas notas em sequencia."

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Emitir Nota</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Selecione quais notas fiscais devem ser emitidas a partir desta OS.</p>"),
                HTML(
                    """
                    <div class="rounded-2xl border border-base-300 bg-base-200/60 p-5 text-base-content/80">
                        <p class="font-semibold mb-2">Como funciona:</p>
                        <ul class="list-disc ml-5 space-y-1 text-sm">
                            <li><strong>NF-e</strong>: abre a etapa de configuracao fiscal dos produtos.</li>
                            <li><strong>NFS-e</strong>: abre a etapa de configuracao fiscal dos servicos.</li>
                            <li><strong>Ambas</strong>: abre as duas etapas e faz a emissao em sequencia na ultima tela.</li>
                        </ul>
                    </div>
                    """
                ),
                Field("note_mode"),
                css_class="space-y-4",
            )
        )

    def clean_note_mode(self) -> str:
        return _resolve_note_mode(self.cleaned_data.get("note_mode"))


class EmissionNfeConfigForm(forms.Form):
    tax_class = forms.ChoiceField(label="Classe de imposto", choices=[])

    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        tax_class_choices = list(kwargs.pop("tax_class_choices", []))
        selected_slider = int(kwargs.pop("selected_slider", 0) or 0)
        super().__init__(*args, **kwargs)

        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(tax_class_choices)
        tax_class_field = self.fields["tax_class"]
        tax_class_field.choices = dropdown_choices
        tax_class_field.widget = SelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe fiscal que sera aplicada aos produtos emitidos na NF-e."
        self._valid_tax_class_refs = {value for value, _ in tax_class_choices if value}

        current_tax_class = str((self.data.get("tax_class") if self.is_bound else self.initial.get("tax_class", "")) or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs and not self.is_bound:
            self.initial["tax_class"] = next(iter(self._valid_tax_class_refs))

        warning_html = ""
        preview_html = ""
        if workorder is not None:
            warning_html, preview_html = _build_nfe_preview_html(workorder=workorder, selected_slider=selected_slider)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>NF-e</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Confira os produtos que serao enviados na NF-e e selecione a classe de imposto.</p>"),
                Field("tax_class"),
                HTML(warning_html),
                HTML(preview_html),
                css_class="space-y-4",
            )
        )

    def clean_tax_class(self) -> str:
        tax_class = str(self.cleaned_data.get("tax_class") or "").strip()
        if self._valid_tax_class_refs and tax_class not in self._valid_tax_class_refs:
            raise forms.ValidationError("Selecione uma classe de imposto valida da lista.")
        return tax_class


class EmissionNfseConfigForm(forms.Form):
    tax_class = forms.ChoiceField(label="Classe de imposto", choices=[])
    service_description = forms.CharField(label="Descricao do servico", required=False, widget=TextareaInput(rows=4))

    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        tax_class_choices = list(kwargs.pop("tax_class_choices", []))
        selected_slider = int(kwargs.pop("selected_slider", 0) or 0)
        super().__init__(*args, **kwargs)

        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(tax_class_choices)
        tax_class_field = self.fields["tax_class"]
        tax_class_field.choices = dropdown_choices
        tax_class_field.widget = SelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe fiscal que sera aplicada ao valor total da NFS-e."
        self._valid_tax_class_refs = {value for value, _ in tax_class_choices if value}

        current_tax_class = str((self.data.get("tax_class") if self.is_bound else self.initial.get("tax_class", "")) or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs and not self.is_bound:
            self.initial["tax_class"] = next(iter(self._valid_tax_class_refs))

        default_service_description = "Prestacao de servico"
        if workorder is not None:
            default_service_description = build_default_service_description_for_workorder(workorder=workorder)
        if not self.is_bound and not str(self.initial.get("service_description") or "").strip():
            self.initial["service_description"] = default_service_description

        warning_html = ""
        preview_html = ""
        if workorder is not None:
            warning_html, preview_html = _build_nfse_preview_html(workorder=workorder, selected_slider=selected_slider)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>NFS-e</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Confira os servicos que compoem a NFS-e, escolha a classe fiscal e revise a descricao.</p>"),
                Div(
                    Field("tax_class", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("service_description", wrapper_class="col-span-12 lg:col-span-8"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                HTML(warning_html),
                HTML(preview_html),
                css_class="space-y-4",
            )
        )

    def clean_tax_class(self) -> str:
        tax_class = str(self.cleaned_data.get("tax_class") or "").strip()
        if self._valid_tax_class_refs and tax_class not in self._valid_tax_class_refs:
            raise forms.ValidationError("Selecione uma classe de imposto valida da lista.")
        return tax_class

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        service_description = str(cleaned_data.get("service_description") or "").strip()
        if not service_description:
            self.add_error("service_description", "Informe a descricao do servico para emitir NFS-e.")
        return cleaned_data
