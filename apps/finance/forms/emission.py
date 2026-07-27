from __future__ import annotations

from datetime import timedelta
from html import escape
from typing import Any

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout
from django import forms
from django.db.models import Exists, OuterRef
from django.urls import reverse
from djmoney.forms import MoneyField
from djmoney.money import Money

from apps.core.presentation.forms import CoreForm
from apps.core.text_normalization import sentence_case
from apps.core.presentation.widgets import DurationInput, MoneyInput, NumberInput, TextareaInput, SearchableSelectInput
from apps.finance.forms.emission_ui import (
    build_slider_widget_attrs,
    build_step5_pricing_panel_data,
    build_step5_preview_oob_html,
    build_step5_summary_layout,
    clamp_slider_value,
    format_money,
)
from apps.core.infrastructure.services.webmania.emission import build_default_service_description_for_workorder, compute_service_discount_for_nfse
from apps.core.infrastructure.services.webmania.nfe_emission import build_nfe_preview_rows, build_nfe_preview_warning_messages, compute_product_discount_for_nfe
from apps.finance.services.pricing import build_emission_pricing_snapshot_for_workorder, build_nfse_service_preview_rows, build_slider_allocation_for_workorder
from apps.finance.models.finance import NfeRequest, NfseRequest
from apps.workorder.models import WorkOrder, WorkOrderStatus


EMISSION_NOTE_TYPE_CHOICES: list[tuple[str, str]] = [("nfe", "Nota Fiscal de Produto"), ("nfse", "Nota Fiscal de Serviço")]
EMISSION_NOTE_MODE_CHOICES: list[tuple[str, str]] = [("nfe", "Nota Fiscal de Produto"), ("nfse", "Nota Fiscal de Serviço"), ("both", "Ambas")]


def _build_modal_action_button(*, label: str, icon: str, url: str) -> str:
    return f"""
        <button type="button"
                class="btn-table-edit"
                hx-get="{url}"
                hx-target="#modal-container"
                hx-swap="innerHTML"
                title="{escape(label)}"
                aria-label="{escape(label)}"
                onclick="window.openEmissionModal && window.openEmissionModal()">
            <span class="material-icons text-base">{icon}</span>
        </button>
    """


def _build_origin_badge(*, label: str, tone: str = "badge-outline") -> str:
    return f'<span class="badge {tone} whitespace-nowrap">{escape(label)}</span>'


def _format_duration_value(duration: timedelta | None) -> str:
    if not duration:
        return "00:00:00"
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _build_step3_rows(*, workorder: WorkOrder) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    product_rows: list[dict[str, Any]] = []
    service_rows: list[dict[str, Any]] = []

    # Prefer WorkOrder._iter_items() so we reuse the nested kit Prefetch from
    # EmissionRequestCreateView._selected_workorder. Chaining prefetch_related
    # on workorder.items after that load raises ValueError (duplicate kit_overrides).
    workorder_items = list(workorder._iter_items())

    for item in workorder_items:
        if item.product_id:
            product_rows.append(
                {
                    "description": str(item.description),
                    "origin": _build_origin_badge(label="Avulso"),
                    "quantity": item.quantity,
                    "unit_price": item.product_selling_price,
                    "total": item.total_price,
                    "edit_url": reverse("finance:emission_workorder_item_edit", kwargs={"workorder_pk": workorder.pk, "item_id": item.pk}),
                }
            )
            continue

        if item.service_id:
            service_rows.append(
                {
                    "description": str(item.description),
                    "origin": _build_origin_badge(label="Avulso"),
                    "quantity": item.quantity,
                    "unit_price": item.service_selling_price,
                    "total": item.total_price,
                    "duration": item.duration_display,
                    "edit_url": reverse("finance:emission_workorder_item_edit", kwargs={"workorder_pk": workorder.pk, "item_id": item.pk}),
                }
            )
            continue

        if not item.kit_id:
            continue

        product_overrides, service_overrides = item._get_kit_override_maps()
        origin_label = f"Kit: {item.kit.name}"

        for kit_product in item._iter_kit_products():
            product = kit_product.product
            override = product_overrides.get(kit_product.product_id)
            per_kit_quantity = int((override.quantity if override else kit_product.quantity) or 0)
            if per_kit_quantity <= 0:
                continue

            effective_quantity = per_kit_quantity * item.quantity
            unit_price = override.product_selling_price if override else product.selling_price
            shipping_total = (override.shipping * item.quantity) if override else Money(0, "BRL")
            total_value = (unit_price * effective_quantity) + shipping_total

            product_rows.append(
                {
                    "description": str(product.name),
                    "origin": _build_origin_badge(label=origin_label, tone="badge-info badge-outline"),
                    "quantity": effective_quantity,
                    "unit_price": unit_price,
                    "total": total_value,
                    "edit_url": reverse(
                        "finance:emission_workorder_kit_component_edit",
                        kwargs={
                            "workorder_pk": workorder.pk,
                            "item_id": item.pk,
                            "component_type": "product",
                            "component_id": product.pk,
                        },
                    ),
                }
            )

        for kit_service in item._iter_kit_services():
            service = kit_service.service
            override = service_overrides.get(kit_service.service_id)
            per_kit_quantity = int((override.quantity if override else kit_service.quantity) or 0)
            if per_kit_quantity <= 0:
                continue

            effective_quantity = per_kit_quantity * item.quantity
            unit_price = override.service_selling_price if override else kit_service.resolved_selling_price
            duration = override.duration if override and override.duration else service.duration
            total_value = unit_price * effective_quantity

            service_rows.append(
                {
                    "description": str(service.name),
                    "origin": _build_origin_badge(label=origin_label, tone="badge-info badge-outline"),
                    "quantity": effective_quantity,
                    "unit_price": unit_price,
                    "total": total_value,
                    "duration": _format_duration_value(duration * effective_quantity if duration else None),
                    "edit_url": reverse(
                        "finance:emission_workorder_kit_component_edit",
                        kwargs={
                            "workorder_pk": workorder.pk,
                            "item_id": item.pk,
                            "component_type": "service",
                            "component_id": service.pk,
                        },
                    ),
                }
            )

    return product_rows, service_rows


def _resolve_note_mode(value: object) -> str:
    note_mode = str(value or "").strip().lower()
    if note_mode in {"nfe", "nfse", "both"}:
        return note_mode
    return "nfe"


def _build_summary_warning_html(*, workorder: WorkOrder, selected_slider: int) -> str:
    allocation = build_slider_allocation_for_workorder(workorder=workorder, slider_override=selected_slider)
    snapshot = build_emission_pricing_snapshot_for_workorder(workorder=workorder, slider_override=selected_slider)
    warnings: list[str] = []

    if allocation.products_target <= 0 or not snapshot.product_lines:
        warnings.append("Com a configuracao atual do slider, nao ha saldo de produtos para emitir Nota Fiscal de Produto.")
    if allocation.services_target <= 0 or not snapshot.service_lines:
        warnings.append("Com a configuracao atual do slider, nao ha saldo de servicos para emitir Nota Fiscal de Serviço.")

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
                    <h3 class="text-xl font-bold text-base-content">Itens consolidados da emissão</h3>
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


def _build_nfe_preview_html(*, workorder: WorkOrder, selected_slider: int, discount_type_override: str = "") -> tuple[str, str]:
    warnings: list[str] = []
    rows, allocation = build_nfe_preview_rows(workorder=workorder, slider_override=selected_slider)

    product_discount = compute_product_discount_for_nfe(
        workorder=workorder,
        products_target=allocation.products_target,
        services_target=allocation.services_target,
        discount_type_override=discount_type_override,
    )
    service_discount = compute_service_discount_for_nfse(
        workorder=workorder,
        discount_type_override=discount_type_override,
    )
    products_net = allocation.products_target - product_discount
    services_net = allocation.services_target - service_discount

    warnings.extend(build_nfe_preview_warning_messages(workorder=workorder, slider_override=selected_slider))
    if allocation.products_target <= 0:
        warnings.append("A configuracao atual do slider nao deixa saldo de produtos para emitir Nota Fiscal de Produto.")

    warning_html = "".join(f"<div class='alert alert-warning'>{escape(message)}</div>" for message in warnings)

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
                {_build_value_card("Produtos", format_money(allocation.products_target), format_money(product_discount), format_money(products_net))}
                {_build_value_card("Serviços", format_money(allocation.services_target), format_money(service_discount), format_money(services_net))}
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


def _build_value_card(label: str, subtotal: str, discount: str, total: str) -> str:
    discount_display = f"- {discount}" if discount and discount != "R$ 0,00" else discount
    return f"""
    <div class="rounded-xl border border-base-300 bg-base-200/50 p-4">
        <p class="text-xs uppercase tracking-wide text-base-content/60 mb-2">{escape(label)}</p>
        <div class="space-y-1 text-sm">
            <div class="flex justify-between">
                <span class="text-base-content/70">Subtotal</span>
                <span class="font-semibold">{subtotal}</span>
            </div>
            <div class="flex justify-between">
                <span class="text-base-content/70">Desconto</span>
                <span class="font-semibold text-error">{discount_display}</span>
            </div>
            <div class="flex justify-between border-t border-base-300 pt-1 font-black text-base">
                <span>Total</span>
                <span>{total}</span>
            </div>
        </div>
    </div>
    """


def _build_nfse_preview_html(*, workorder: WorkOrder, selected_slider: int, discount_type_override: str = "") -> tuple[str, str]:
    allocation = build_slider_allocation_for_workorder(workorder=workorder, slider_override=selected_slider)
    warning_html = ""
    if allocation.services_target <= 0:
        warning_html = "<div class='alert alert-warning'>A configuracao atual do slider nao deixa saldo de servicos para emitir Nota Fiscal de Serviço.</div>"

    product_discount = compute_product_discount_for_nfe(
        workorder=workorder,
        products_target=allocation.products_target,
        services_target=allocation.services_target,
        discount_type_override=discount_type_override,
    )
    service_discount = compute_service_discount_for_nfse(
        workorder=workorder,
        discount_type_override=discount_type_override,
    )
    products_net = allocation.products_target - product_discount
    services_net = allocation.services_target - service_discount

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
                {_build_value_card("Serviços", format_money(allocation.services_target), format_money(service_discount), format_money(services_net))}
                {_build_value_card("Produtos", format_money(allocation.products_target), format_money(product_discount), format_money(products_net))}
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


class EmissionKitProductComponentForm(CoreForm):
    quantity = forms.IntegerField(label="Quantidade por kit", min_value=0, widget=NumberInput())
    cost = MoneyField(label="Custo do produto", required=False, widget=MoneyInput())
    price = MoneyField(label="Valor de venda", required=False, widget=MoneyInput())
    shipping = MoneyField(label="Frete por kit", required=False, widget=MoneyInput())

    def __init__(self, *args, parent_quantity: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        if parent_quantity > 1:
            self.fields["quantity"].help_text = f"Este kit aparece {parent_quantity}x na O.S.; o total final sera multiplicado por essa quantidade."


class EmissionKitServiceComponentForm(CoreForm):
    quantity = forms.IntegerField(label="Quantidade por kit", min_value=0, widget=NumberInput())
    cost = MoneyField(label="Custo do servico", required=False, widget=MoneyInput())
    price = MoneyField(label="Valor de venda", required=False, widget=MoneyInput())
    duration = forms.DurationField(label="Duracao por kit", required=False, widget=DurationInput())

    def __init__(self, *args, parent_quantity: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        if parent_quantity > 1:
            self.fields["quantity"].help_text = f"Este kit aparece {parent_quantity}x na O.S.; o total final sera multiplicado por essa quantidade."


class EmissionStep1Form(CoreForm):
    workorder = forms.ModelChoiceField(queryset=WorkOrder.objects.none(), label="Ordem de Servico")

    def __init__(self, *args, **kwargs):
        workshop = kwargs.pop("workshop", None)
        super().__init__(*args, **kwargs)

        queryset = WorkOrder.objects.none()
        if workshop is not None:
            nfe_exists = NfeRequest.objects.filter(workorder=OuterRef("pk"))
            nfse_exists = NfseRequest.objects.filter(workorder=OuterRef("pk"))

            queryset = (
                WorkOrder.objects.filter(workshop=workshop, status=WorkOrderStatus.APPROVED)
                .select_related("budget", "budget__customer", "budget__vehicle")
                .annotate(has_emission=Exists(nfe_exists) | Exists(nfse_exists))
                .filter(has_emission=False)
            )

        field = self.fields["workorder"]
        field.queryset = queryset.order_by("-id")

        def _label_from_instance(workorder: WorkOrder) -> str:
            customer = getattr(getattr(workorder, "budget", None), "customer", None)
            customer_name = customer.name if customer else "Cliente nao informado"
            return f"Ordem de Servico {workorder.get_id} - {customer_name}"

        field.label_from_instance = _label_from_instance
        field.widget = SearchableSelectInput(choices=list(field.choices))

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Selecionar Ordem de Servico</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Selecione a OS aprovada que sera usada na emissão fiscal.</p>"),
                Field("workorder"),
                css_class="space-y-4",
            )
        )


class EmissionStep2Form(CoreForm):
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
        customer_action_html = _build_modal_action_button(label="Editar cliente", icon="edit", url=reverse("customer:quick_update", kwargs={"pk": customer.pk})) if customer else ""
        vehicle_action_html = _build_modal_action_button(label="Editar veiculo", icon="directions_car_filled", url=reverse("customer:vehicle_quick_update", kwargs={"pk": vehicle.pk})) if vehicle else ""

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir cliente</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Revise os dados do cliente e do veiculo antes de seguir. Se precisar, faca um ajuste rapido sem sair da emissão.</p>"),
                HTML(
                    f"""
                    <div class="grid grid-cols-1 gap-6">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 bg-base-200 p-5 rounded-xl">
                            <div class="md:col-span-2 flex items-center justify-between gap-3 flex-wrap">
                                <div>
                                    <p class="text-xs uppercase text-base-content/60">Cliente</p>
                                    <p class="text-lg font-bold text-base-content">{customer_name}</p>
                                </div>
                                {customer_action_html}
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
                        </div>
                        <div class="grid grid-cols-1 gap-4 bg-base-200 p-5 rounded-xl">
                            <div class="flex items-center justify-between gap-3 flex-wrap">
                                <div>
                                    <p class="text-xs uppercase text-base-content/60">Veiculo</p>
                                    <p class="text-lg font-bold text-base-content">{vehicle_label}</p>
                                </div>
                                {vehicle_action_html}
                            </div>
                            <p class="text-sm text-base-content/70">As alterações do veiculo sao globais e refletem em toda a oficina.</p>
                        </div>
                    </div>
                    """
                ),
                css_class="space-y-4",
            )
        )


class EmissionStep3Form(CoreForm):
    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        super().__init__(*args, **kwargs)

        products_html = ""
        services_html = ""
        total_products = format_money(0)
        total_services = format_money(0)

        if workorder is not None:
            product_rows, service_rows = _build_step3_rows(workorder=workorder)

            total_products = format_money(sum((row["total"] for row in product_rows), Money(0, "BRL")))
            total_services = format_money(sum((row["total"] for row in service_rows), Money(0, "BRL")))

            products_html = "".join(
                f"""
                <tr class="border-b border-base-300/60">
                    <td class="py-2">{escape(str(row["description"]))}</td>
                    <td class="py-2 text-center">{row["quantity"]}</td>
                    <td class="py-2 text-right">{format_money(row["unit_price"])}</td>
                    <td class="py-2 text-right font-semibold">{format_money(row["total"])}</td>
                    <td class="py-2 text-center">
                        {_build_modal_action_button(label="Editar", icon="edit", url=row["edit_url"])}
                    </td>
                </tr>
                """
                for row in product_rows
            )
            services_html = "".join(
                f"""
                <tr class="border-b border-base-300/60">
                    <td class="py-2">{escape(str(row["description"]))}</td>
                    <td class="py-2 text-center">{row["quantity"]}</td>
                    <td class="py-2 text-right">{format_money(row["unit_price"])}</td>
                    <td class="py-2 text-right font-semibold">{format_money(row["total"])}</td>
                    <td class="py-2 text-center">
                        {_build_modal_action_button(label="Editar", icon="edit", url=row["edit_url"])}
                    </td>
                </tr>
                """
                for row in service_rows
            )

        if not products_html:
            products_html = """
            <tr>
                <td colspan="6" class="py-4 text-center text-base-content/60">Nenhum produto editavel encontrado nesta OS.</td>
            </tr>
            """

        if not services_html:
            services_html = """
            <tr>
                <td colspan="6" class="py-4 text-center text-base-content/60">Nenhum servico editavel encontrado nesta OS.</td>
            </tr>
            """

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Conferir produtos e servicos</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Revise os produtos e servicos da O.S., inclusive os que vieram de kits, e edite rapidamente o que for necessario antes de definir o tipo da nota.</p>"),
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
                                        <th class="text-right">Valor Unitário</th>
                                        <th class="text-right">Total</th>
                                        <th class="text-center">Ações</th>
                                    </tr>
                                </thead>
                                <tbody>{products_html}</tbody>
                                <tfoot>
                                    <tr>
                                        <th colspan="4" class="text-right">Total Produtos</th>
                                        <th class="text-right">{total_products}</th>
                                        <th></th>
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
                                        <th class="text-right">Valor Unitário</th>
                                        <th class="text-right">Total</th>
                                        <th class="text-center">Ações</th>
                                    </tr>
                                </thead>
                                <tbody>{services_html}</tbody>
                                <tfoot>
                                    <tr>
                                        <th colspan="4" class="text-right">Total Servicos</th>
                                        <th class="text-right">{total_services}</th>
                                        <th></th>
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


class EmissionStep4Form(CoreForm):
    pricing_slider = forms.IntegerField(label="", min_value=-100, max_value=100)

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
                HTML("<p class='text-base-content/70 mb-6'>Ajuste o slider e revise todos os produtos e servicos com os valores finais da emissão.</p>"),
                build_step5_summary_layout(prefix="emission", panel_data=panel_data, slider_field_name="pricing_slider", form_selector="#emission-form", body_html=body_html) if panel_data is not None else HTML(""),
                css_class="space-y-4",
            )
        )

    def clean_pricing_slider(self) -> int:
        return clamp_slider_value(self.cleaned_data.get("pricing_slider"), default=0)


class EmissionStep5Form(CoreForm):
    note_mode = forms.ChoiceField(label="Tipo de notas fiscais", choices=EMISSION_NOTE_MODE_CHOICES)

    def __init__(self, *args, **kwargs):
        note_mode_choices = kwargs.pop("note_mode_choices", EMISSION_NOTE_MODE_CHOICES)
        allowed_note_modes = set(kwargs.pop("allowed_note_modes", {"nfe", "nfse", "both"}))
        availability_message = str(kwargs.pop("availability_message", "") or "").strip()
        super().__init__(*args, **kwargs)

        note_mode_field = self.fields["note_mode"]
        note_mode_field.choices = list(note_mode_choices)
        note_mode_field.widget = SearchableSelectInput(choices=list(note_mode_choices))
        note_mode_field.help_text = "Escolha se a emissão sera somente de produtos, somente de servicos, ou das duas notas em sequencia."

        selected_note_mode = str((self.data.get("note_mode") if self.is_bound else self.initial.get("note_mode", "")) or "").strip()
        if selected_note_mode not in allowed_note_modes:
            if "both" in allowed_note_modes:
                selected_note_mode = "both"
            elif "nfe" in allowed_note_modes:
                selected_note_mode = "nfe"
            elif "nfse" in allowed_note_modes:
                selected_note_mode = "nfse"
            else:
                selected_note_mode = ""
            if not self.is_bound:
                self.initial["note_mode"] = selected_note_mode

        option_cards_html = "".join(
            self._build_note_mode_option_html(
                value=value,
                label=label,
                checked=value == selected_note_mode,
                disabled=value not in allowed_note_modes,
            )
            for value, label in note_mode_choices
        )

        availability_notice_html = ""
        if availability_message:
            availability_notice_html = f"<div class='alert alert-info'>{availability_message}</div>"

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
                            <li><strong>Nota Fiscal de Produto</strong>: abre a etapa de configuracao fiscal dos produtos.</li>
                            <li><strong>Nota Fiscal de Serviço</strong>: abre a etapa de configuracao fiscal dos servicos.</li>
                            <li><strong>Ambas</strong>: abre as duas etapas e faz a emissão em sequencia na ultima tela.</li>
                        </ul>
                    </div>
                    """
                ),
                HTML(availability_notice_html),
                HTML(f"<div class='grid grid-cols-1 lg:grid-cols-3 gap-4'>{option_cards_html}</div>"),
                css_class="space-y-4",
            )
        )

        self._allowed_note_modes = allowed_note_modes

    @staticmethod
    def _build_note_mode_option_html(*, value: str, label: str, checked: bool, disabled: bool) -> str:
        disabled_class = "opacity-50 cursor-not-allowed" if disabled else "cursor-pointer hover:border-primary/50"
        checked_class = "border-primary ring-2 ring-primary/20" if checked else "border-base-300"
        disabled_attr = "disabled" if disabled else ""
        checked_attr = "checked" if checked else ""
        return f"""
            <label class="flex items-start gap-3 rounded-2xl border bg-base-100 p-5 transition {checked_class} {disabled_class}">
                <input type="radio" name="note_mode" value="{value}" class="radio radio-primary mt-1" {checked_attr} {disabled_attr}>
                <div>
                    <div class="font-semibold text-base-content">{label}</div>
                    <div class="text-sm text-base-content/70 mt-1">{"Indisponível com a configuração atual." if disabled else "Disponível para emissão nesta configuração."}</div>
                </div>
            </label>
        """

    def clean_note_mode(self) -> str:
        note_mode = _resolve_note_mode(self.cleaned_data.get("note_mode"))
        if note_mode not in self._allowed_note_modes:
            raise forms.ValidationError("Selecione um tipo de nota fiscal disponível para a configuração atual.")
        return note_mode


class EmissionNfeConfigForm(CoreForm):
    tax_class = forms.ChoiceField(label="Classe de imposto", choices=[])
    additional_information = forms.CharField(label="Observacao da nota", required=False, widget=TextareaInput(rows=4))

    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        tax_class_choices = list(kwargs.pop("tax_class_choices", []))
        selected_slider = int(kwargs.pop("selected_slider", 0) or 0)
        discount_type_override = str(kwargs.pop("discount_type_override", "") or "")
        super().__init__(*args, **kwargs)

        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(tax_class_choices)
        tax_class_field = self.fields["tax_class"]
        tax_class_field.choices = dropdown_choices
        tax_class_field.widget = SearchableSelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe fiscal que sera aplicada aos produtos emitidos na Nota Fiscal de Produto."
        self._valid_tax_class_refs = {value for value, _ in tax_class_choices if value}

        additional_information_field = self.fields["additional_information"]
        additional_information_field.help_text = "Enviada como informacao complementar junto com a Nota Fiscal de Produto."

        current_tax_class = str((self.data.get("tax_class") if self.is_bound else self.initial.get("tax_class", "")) or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs and not self.is_bound:
            self.initial["tax_class"] = next(iter(self._valid_tax_class_refs))

        warning_html = ""
        preview_html = ""
        if workorder is not None:
            warning_html, preview_html = _build_nfe_preview_html(workorder=workorder, selected_slider=selected_slider, discount_type_override=discount_type_override)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Nota Fiscal de Produto</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Confira os produtos que serão enviados na Nota Fiscal de Produto e selecione a classe de imposto.</p>"),
                Field("tax_class"),
                Field("additional_information"),
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

    def clean_additional_information(self) -> str:
        value = str(self.cleaned_data.get("additional_information") or "").strip()
        return sentence_case(value) if value else value


class EmissionNfseConfigForm(CoreForm):
    tax_class = forms.ChoiceField(label="Classe de imposto", choices=[])
    service_description = forms.CharField(label="Descricao do servico", required=False, widget=TextareaInput(rows=4))
    additional_information = forms.CharField(label="Observacao da nota", required=False, widget=TextareaInput(rows=4))

    def __init__(self, *args, **kwargs):
        workorder = kwargs.pop("workorder", None)
        tax_class_choices = list(kwargs.pop("tax_class_choices", []))
        selected_slider = int(kwargs.pop("selected_slider", 0) or 0)
        discount_type_override = str(kwargs.pop("discount_type_override", "") or "")
        super().__init__(*args, **kwargs)

        dropdown_choices = [("", "Selecione a classe de imposto")]
        dropdown_choices.extend(tax_class_choices)
        tax_class_field = self.fields["tax_class"]
        tax_class_field.choices = dropdown_choices
        tax_class_field.widget = SearchableSelectInput(choices=dropdown_choices)
        tax_class_field.help_text = "Classe fiscal que sera aplicada ao valor total da Nota Fiscal de Serviço."
        self._valid_tax_class_refs = {value for value, _ in tax_class_choices if value}

        current_tax_class = str((self.data.get("tax_class") if self.is_bound else self.initial.get("tax_class", "")) or "").strip()
        if self._valid_tax_class_refs and current_tax_class not in self._valid_tax_class_refs and not self.is_bound:
            self.initial["tax_class"] = next(iter(self._valid_tax_class_refs))

        default_service_description = "Prestacao de servico"
        if workorder is not None:
            default_service_description = build_default_service_description_for_workorder(workorder=workorder)
        if not self.is_bound and not str(self.initial.get("service_description") or "").strip():
            self.initial["service_description"] = default_service_description

        additional_information_field = self.fields["additional_information"]
        additional_information_field.help_text = "Enviada como informacao complementar quando o provedor da Nota Fiscal de Serviço suportar esse campo."

        warning_html = ""
        preview_html = ""
        if workorder is not None:
            warning_html, preview_html = _build_nfse_preview_html(workorder=workorder, selected_slider=selected_slider, discount_type_override=discount_type_override)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                HTML("<h2 class='text-2xl font-bold'>Nota Fiscal de Serviço</h2>"),
                HTML("<p class='text-base-content/70 mb-6'>Confira os serviços que compõem a Nota Fiscal de Serviço, escolha a classe fiscal e revise a descrição.</p>"),
                Div(
                    Field("tax_class", wrapper_class="col-span-12 lg:col-span-4"),
                    Field("service_description", wrapper_class="col-span-12 lg:col-span-8"),
                    css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
                ),
                Field("additional_information"),
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
            self.add_error("service_description", "Informe a descricao do servico para emitir Nota Fiscal de Serviço.")
        return cleaned_data

    def clean_service_description(self) -> str:
        value = str(self.cleaned_data.get("service_description") or "").strip()
        return sentence_case(value) if value else value

    def clean_additional_information(self) -> str:
        value = str(self.cleaned_data.get("additional_information") or "").strip()
        return sentence_case(value) if value else value
