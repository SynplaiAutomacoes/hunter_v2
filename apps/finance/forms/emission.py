from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms
from django.urls import reverse

from apps.core.widgets import SelectInput, TextareaInput
from apps.finance.services.emission import build_default_service_description_for_workorder
from apps.finance.services.nfe_emission import NfeEmissionError, build_nfe_preview_rows
from apps.finance.services.pricing import build_emission_pricing_snapshot_for_workorder, build_slider_allocation_for_workorder
from apps.workorder.models import WorkOrder, WorkOrderStatus


EMISSION_NOTE_TYPE_CHOICES: list[tuple[str, str]] = [
    ("nfe", "NF-e"),
    ("nfse", "NFS-e"),
]


def _format_money(value: Any) -> str:
    amount: Decimal
    if hasattr(value, "amount"):
        amount = value.amount
    else:
        amount = Decimal(str(value or 0))
    return f"R$ {amount:.2f}".replace(".", ",")


def _coerce_slider(value: object, default: int = 0) -> int:
    try:
        slider_source = default if value in (None, "") else str(value)
        return max(-100, min(100, int(slider_source)))
    except (TypeError, ValueError):
        return max(-100, min(100, int(default)))


def _resolve_note_type(value: object) -> str:
    note_type = str(value or "").strip().lower()
    if note_type in {"nfe", "nfse"}:
        return note_type
    return "nfe"


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
        total_products = _format_money(0)
        total_services = _format_money(0)

        if workorder is not None:
            snapshot = build_emission_pricing_snapshot_for_workorder(workorder=workorder)
            total_products = _format_money(snapshot.total_products_value)
            total_services = _format_money(snapshot.total_services_value)

            products_html = "".join(
                f"""
                <tr class="border-b border-base-300/60">
                    <td class="py-2">{escape(str(line.description))}</td>
                    <td class="py-2 text-center">{line.quantity}</td>
                    <td class="py-2 text-right">{_format_money(line.raw_total)}</td>
                </tr>
                """
                for line in snapshot.product_lines
            )
            services_html = "".join(
                f"""
                <tr class="border-b border-base-300/60">
                    <td class="py-2">{escape(str(line.description))}</td>
                    <td class="py-2 text-center">{line.quantity}</td>
                    <td class="py-2 text-right">{_format_money(line.raw_total)}</td>
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
    note_type = forms.ChoiceField(label="Tipo de nota", choices=EMISSION_NOTE_TYPE_CHOICES)
    pricing_slider = forms.IntegerField(label="Slider da emissao", min_value=-100, max_value=100)
    tax_class = forms.ChoiceField(label="Classe de imposto", choices=[])
    service_description = forms.CharField(label="Descricao do servico", required=False, widget=TextareaInput(rows=4))

    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        note_type_choices = kwargs.pop("note_type_choices", EMISSION_NOTE_TYPE_CHOICES)
        tax_class_choices_by_type = kwargs.pop("tax_class_choices_by_type", {})
        super().__init__(*args, **kwargs)

        selected_note_type = _resolve_note_type(self.data.get("note_type") if self.is_bound else self.initial.get("note_type"))
        initial_slider = self.initial.get("pricing_slider", getattr(getattr(workorder, "budget", None), "slider", 0))
        selected_slider = _coerce_slider(self.data.get("pricing_slider") if self.is_bound else initial_slider, default=int(initial_slider or 0))

        note_type_field = self.fields["note_type"]
        note_type_field.choices = list(note_type_choices)
        note_type_field.widget = SelectInput(choices=list(note_type_choices))
        note_type_field.widget.attrs.update(
            {
                "hx-get": reverse("finance:emission_preview"),
                "hx-trigger": "change",
                "hx-target": "#emission-step4-body",
                "hx-swap": "outerHTML",
                "hx-include": "#emission-form",
            }
        )
        note_type_field.help_text = "Escolha se a emissao sera de produto ou de servico."

        slider_field = self.fields["pricing_slider"]
        slider_field.widget = forms.NumberInput(
            attrs={
                "type": "range",
                "min": "-100",
                "max": "100",
                "step": "1",
                "class": "w-full centered-range emission-centered-range",
                "hx-get": reverse("finance:emission_preview"),
                "hx-trigger": "input changed delay:250ms",
                "hx-target": "#emission-step4-body",
                "hx-swap": "outerHTML",
                "hx-include": "#emission-form",
            }
        )
        slider_field.help_text = "Negativo prioriza produtos. Positivo prioriza servicos."

        tax_class_choices = list(tax_class_choices_by_type.get(selected_note_type, []))
        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(tax_class_choices)

        tax_class_field = self.fields["tax_class"]
        tax_class_field.choices = dropdown_choices
        tax_class_field.widget = SelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe fiscal correspondente ao tipo de nota selecionado."
        self._valid_tax_class_refs = {value for value, _ in tax_class_choices if value}

        current_tax_class = str(self.data.get("tax_class") if self.is_bound else self.initial.get("tax_class", "") or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs:
            replacement_tax_class = next(iter(self._valid_tax_class_refs))
            if self.is_bound:
                mutable_data = self.data.copy()
                mutable_data["tax_class"] = replacement_tax_class
                self.data = mutable_data
            else:
                self.initial["tax_class"] = replacement_tax_class

        default_service_description = "Prestacao de servico"
        if workorder is not None:
            default_service_description = build_default_service_description_for_workorder(workorder=workorder)

        if selected_note_type == "nfse":
            self.fields["service_description"].required = True
            current_service_description = str(self.data.get("service_description") if self.is_bound else self.initial.get("service_description") or "").strip()
            if not current_service_description:
                if self.is_bound:
                    mutable_data = self.data.copy()
                    mutable_data["service_description"] = default_service_description
                    self.data = mutable_data
                else:
                    self.initial["service_description"] = default_service_description
        else:
            self.fields["service_description"].required = False

        preview_warning = ""
        preview_html = ""
        total_to_emit = _format_money(0)
        complementary_total = _format_money(0)
        complementary_label = "Saldo complementar"

        if workorder is not None:
            allocation = build_slider_allocation_for_workorder(workorder=workorder, slider_override=selected_slider)
            if selected_note_type == "nfe":
                complementary_label = "Saldo NFS-e (servicos)"
                total_to_emit = _format_money(allocation.products_target)
                complementary_total = _format_money(allocation.services_target)
                if allocation.products_target <= 0:
                    preview_warning = "<div class='alert alert-warning mb-4'>A configuracao atual do slider nao deixa saldo de produtos para emitir NF-e.</div>"
                try:
                    rows, _ = build_nfe_preview_rows(workorder=workorder, slider_override=selected_slider)
                except NfeEmissionError as exc:
                    rows = []
                    preview_warning = f"<div class='alert alert-warning mb-4'>{escape(str(exc))}</div>"

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
                        <td colspan="4" class="py-4 text-center text-base-content/60">Nenhum produto elegivel para emissao com a configuracao atual.</td>
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
                            <tbody>{rows_html}</tbody>
                            <tfoot>
                                <tr>
                                    <th colspan="3" class="text-right">Total NF-e (produtos)</th>
                                    <th class="text-right">{total_to_emit}</th>
                                </tr>
                                <tr>
                                    <th colspan="3" class="text-right">{complementary_label}</th>
                                    <th class="text-right">{complementary_total}</th>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                """
            else:
                complementary_label = "Saldo NF-e (produtos)"
                total_to_emit = _format_money(allocation.services_target)
                complementary_total = _format_money(allocation.products_target)
                if allocation.services_target <= 0:
                    preview_warning = "<div class='alert alert-warning mb-4'>A configuracao atual do slider nao deixa saldo de servicos para emitir NFS-e.</div>"

                snapshot = build_emission_pricing_snapshot_for_workorder(workorder=workorder, slider_override=selected_slider)
                rows_html = "".join(
                    f"""
                    <tr class="border-b border-base-300/60">
                        <td class="py-2">{escape(str(line.description))}</td>
                        <td class="py-2 text-center">{line.quantity}</td>
                        <td class="py-2 text-right">{_format_money(line.raw_total)}</td>
                    </tr>
                    """
                    for line in snapshot.service_lines
                )
                if not rows_html:
                    rows_html = """
                    <tr>
                        <td colspan="3" class="py-4 text-center text-base-content/60">Nenhum servico elegivel para esta OS.</td>
                    </tr>
                    """
                preview_html = f"""
                    <div class="overflow-x-auto mb-6">
                        <table class="table table-zebra">
                            <thead>
                                <tr>
                                    <th>Servico</th>
                                    <th class="text-center">Qtd</th>
                                    <th class="text-right">Total Base</th>
                                </tr>
                            </thead>
                            <tbody>{rows_html}</tbody>
                            <tfoot>
                                <tr>
                                    <th colspan="2" class="text-right">Total NFS-e (servicos)</th>
                                    <th class="text-right">{total_to_emit}</th>
                                </tr>
                                <tr>
                                    <th colspan="2" class="text-right">{complementary_label}</th>
                                    <th class="text-right">{complementary_total}</th>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                """

        slider_indicator = f"""
            <style>
                input[type="range"].emission-centered-range {{
                    -webkit-appearance: none;
                    -moz-appearance: none;
                    width: 100%;
                    height: 8px;
                    background: transparent;
                }}

                input[type="range"].emission-centered-range::-webkit-slider-runnable-track {{
                    height: 8px;
                    border-radius: 999px;
                    background: linear-gradient(
                        to right,
                        #dbeafe var(--left),
                        #0f766e var(--left),
                        #0f766e var(--right),
                        #fde68a var(--right)
                    );
                }}

                input[type="range"].emission-centered-range::-webkit-slider-thumb {{
                    -webkit-appearance: none;
                    width: 24px;
                    height: 24px;
                    background: #0f172a;
                    border: 3px solid #f8fafc;
                    border-radius: 999px;
                    margin-top: -8px;
                    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.22);
                    cursor: pointer;
                }}

                input[type="range"].emission-centered-range::-moz-range-track {{
                    height: 8px;
                    border-radius: 999px;
                    background: linear-gradient(
                        to right,
                        #dbeafe var(--left),
                        #0f766e var(--left),
                        #0f766e var(--right),
                        #fde68a var(--right)
                    );
                }}

                input[type="range"].emission-centered-range::-moz-range-thumb {{
                    width: 24px;
                    height: 24px;
                    background: #0f172a;
                    border: 3px solid #f8fafc;
                    border-radius: 999px;
                    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.22);
                    cursor: pointer;
                }}
            </style>
            <div class="rounded-2xl border border-base-300 bg-base-100/90 p-5 shadow-sm">
                <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between mb-4">
                    <div>
                        <p class="text-xs uppercase tracking-[0.24em] text-base-content/50">Ajuste fiscal</p>
                        <h3 class="text-lg font-semibold">Slider da emissao</h3>
                        <p class="text-sm text-base-content/70">Comeca com o valor do orcamento, mas aqui fica independente e nao sincroniza de volta.</p>
                    </div>
                    <div class="badge badge-outline badge-lg px-4 py-3" id="emission-slider-value">{selected_slider}</div>
                </div>
                <div class="grid gap-3 sm:grid-cols-2 mb-4">
                    <div class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-900">
                        <p class="text-xs uppercase tracking-wide text-emerald-700/80">Peso em produtos</p>
                        <p class="text-2xl font-black"><span id="val-produtos">{abs(selected_slider) if selected_slider < 0 else 0}</span>%</p>
                    </div>
                    <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-900">
                        <p class="text-xs uppercase tracking-wide text-amber-700/80">Peso em servicos</p>
                        <p class="text-2xl font-black"><span id="val-servicos">{selected_slider if selected_slider > 0 else 0}</span>%</p>
                    </div>
                </div>
                <p class="text-sm font-medium text-base-content/60 mb-2">Deslize para a esquerda para fortalecer produtos; para a direita para fortalecer servicos.</p>
            </div>
        """

        service_description_field = []
        if selected_note_type == "nfse":
            service_description_field = [Field("service_description", wrapper_class="col-span-12")]

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Emitir nota</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Escolha o tipo da nota, ajuste o slider se necessario e confira a previa antes de emitir.</p>"),
                HTML(slider_indicator),
                HTML(preview_warning),
                HTML(preview_html),
                Div(
                    Field("note_type", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("pricing_slider", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("tax_class", wrapper_class="col-span-12 lg:col-span-4"),
                    *service_description_field,
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                HTML(
                    """
                    <script>
                        (function () {
                            window.initEmissionSliderPreview = function initEmissionSliderPreview() {
                                const slider = document.querySelector('input[name="pricing_slider"]');
                                const badge = document.getElementById('emission-slider-value');
                                const productsLabel = document.getElementById('val-produtos');
                                const servicesLabel = document.getElementById('val-servicos');

                                if (!slider) return;

                                function updateFill(rawValue) {
                                    const value = parseInt(rawValue || 0, 10) || 0;
                                    const min = -100;
                                    const max = 100;
                                    const center = 50;
                                    const percent = ((value - min) / (max - min)) * 100;

                                    if (value === 0) {
                                        slider.style.setProperty('--left', center + '%');
                                        slider.style.setProperty('--right', center + '%');
                                    } else if (value < 0) {
                                        slider.style.setProperty('--left', percent + '%');
                                        slider.style.setProperty('--right', center + '%');
                                    } else {
                                        slider.style.setProperty('--left', center + '%');
                                        slider.style.setProperty('--right', percent + '%');
                                    }

                                    if (badge) badge.textContent = value;
                                    if (productsLabel) productsLabel.textContent = value < 0 ? Math.abs(value) : 0;
                                    if (servicesLabel) servicesLabel.textContent = value > 0 ? value : 0;
                                }

                                slider.oninput = function () { updateFill(slider.value); };
                                updateFill(slider.value || 0);
                            };

                            document.addEventListener('DOMContentLoaded', window.initEmissionSliderPreview);
                            document.body.addEventListener('htmx:afterSettle', window.initEmissionSliderPreview);
                        })();
                    </script>
                    """
                ),
                css_class="space-y-4",
            )
        )

    def clean_tax_class(self) -> str:
        tax_class = str(self.cleaned_data.get("tax_class") or "").strip()
        if self._valid_tax_class_refs and tax_class not in self._valid_tax_class_refs:
            raise forms.ValidationError("Selecione uma classe de imposto valida da lista.")
        return tax_class

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        note_type = _resolve_note_type(cleaned_data.get("note_type"))
        service_description = str(cleaned_data.get("service_description") or "").strip()

        if note_type == "nfse" and not service_description:
            self.add_error("service_description", "Informe a descricao do servico para emitir NFS-e.")

        if note_type != "nfse":
            cleaned_data["service_description"] = ""

        return cleaned_data
