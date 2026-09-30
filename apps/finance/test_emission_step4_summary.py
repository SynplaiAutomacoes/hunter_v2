from __future__ import annotations

from datetime import date, timedelta

from crispy_forms.utils import render_crispy_form
from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.finance.forms.emission import EmissionStep4Form
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


class EmissionStep4SummaryLayoutTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Resumo Emissão",
            cnpj="12.345.678/0001-91",
            phone="+5511987654322",
            address="Rua Resumo, 200",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Resumo")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="RES-P-1",
            name="Filtro de Óleo",
            unit=Product.Unit.UND,
            cost_price=Money("20.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Troca de Óleo",
            duration=timedelta(hours=1),
            suggested_cost=Money("30.00", "BRL"),
            selling_price=Money("200.00", "BRL"),
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 24),
            status=BudgetStatus.APPROVED,
            current_step=6,
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            product=self.product,
            description="Filtro de Óleo",
            quantity=1,
            product_cost_price=Money("20.00", "BRL"),
            product_selling_price=Money("100.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            service=self.service,
            description="Troca de Óleo",
            quantity=1,
            service_cost_price=Money("30.00", "BRL"),
            service_selling_price=Money("200.00", "BRL"),
        )

    def _build_form(self, *, slider: int) -> EmissionStep4Form:
        return EmissionStep4Form(
            {
                "pricing_slider": str(slider),
                "note_mode": "both",
                "discount_value_override_0": "0.00",
                "discount_value_override_1": "BRL",
            },
            workorder=self.workorder,
            allowed_note_modes={"nfe", "nfse", "both"},
        )

    def test_summary_layout_does_not_render_hunter_pricing_panel(self) -> None:
        rendered = render_crispy_form(self._build_form(slider=0))

        self.assertNotIn("Método Hunter", rendered)
        self.assertNotIn("Rentabilidade", rendered)
        self.assertIn("Itens consolidados da emissão", rendered)
        self.assertIn("Valor Unitário", rendered)
        self.assertIn("Desconto na nota", rendered)
        self.assertIn("discount_value_override", rendered)

    def test_preview_oob_html_skips_pricing_panel_spans(self) -> None:
        form = self._build_form(slider=0)

        self.assertNotIn("display-venda-pecas", form.preview_panel_html)
        self.assertNotIn("display-venda-mo", form.preview_panel_html)
        self.assertIn('id="emission-preview-block"', form.preview_panel_html)

    def test_slider_changes_unit_and_total_values_of_each_line(self) -> None:
        neutral_preview = self._build_form(slider=0).preview_html
        shifted_preview = self._build_form(slider=100).preview_html

        self.assertIn("R$ 100,00", neutral_preview)
        self.assertIn("R$ 200,00", neutral_preview)
        self.assertIn("R$ 300,00", shifted_preview)
        self.assertIn("R$ 0,00", shifted_preview)

    def test_slider_widget_updates_preview_while_dragging(self) -> None:
        widget_attrs = self._build_form(slider=0).fields["pricing_slider"].widget.attrs

        self.assertIn("input", widget_attrs["hx-trigger"])
        self.assertIn("delay:", widget_attrs["hx-trigger"])
