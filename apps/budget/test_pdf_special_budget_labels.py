from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone

from apps.budget.models import BudgetType


class BudgetPdfSpecialBudgetLabelTests(SimpleTestCase):
    templates = (
        "budget/partials/pdf/visualizarPDF.html",
        "budget/partials/pdf/visualizarPDFGestor.html",
        "budget/partials/pdf/visualizarPDFMecanico.html",
    )

    def _render_pdf_template(self, template_name: str, budget_type: BudgetType) -> str:
        is_courtesy_budget = budget_type == BudgetType.COURTESY
        is_warranty_budget = budget_type == BudgetType.WARRANTY
        special_budget_label = "Orçamento de Cortesia" if is_courtesy_budget else "Orçamento de Garantia" if is_warranty_budget else ""
        created_at = timezone.make_aware(datetime(2026, 7, 1, 10, 30))

        budget = SimpleNamespace(
            id=123,
            budget_type=budget_type,
            is_warranty_budget=is_warranty_budget,
            workshop=SimpleNamespace(name="Oficina Teste", cnpj="11222333000144", address="Rua Teste, 123", pdf_phone="11999999999", pdf_observation=""),
            customer=SimpleNamespace(name="Cliente Teste", cpf_or_cnpj="12345678909", phone="11988887777", email="", bairro="", cidade="", estado="", logradouro="", numero="", cep=""),
            vehicle=SimpleNamespace(plate="ABC1D23", brand="Marca", model="Modelo", engine="", fuel="", year_model="", year_fabrication="", color=""),
            created=created_at,
            criado_em=created_at,
            customer_agreed_departure_at=None,
            problem_description="",
            technical_diagnosis="",
            current_km=0,
            total_costs_products_value="R$ 0,00",
            rentability=100,
            budget_status="Em aberto",
        )
        context = {
            "budget": budget,
            "workorder": SimpleNamespace(delivered_at=None),
            "workshop_logo_data_uri": "",
            "is_warranty_or_courtesy": bool(special_budget_label),
            "special_budget_label": special_budget_label,
            "pages": [SimpleNamespace(produtos=[], servicos=[])],
            "produtos": [],
            "servicos": [],
            "payments": [],
            "total_produtos": "R$ 0,00",
            "total_servicos": "R$ 0,00",
            "total_geral": "R$ 0,00",
            "benefit_label": "Cortesia" if is_courtesy_budget else "Garantia" if is_warranty_budget else "",
            "benefit_total": "R$ 0,00",
            "total_a_pagar": "R$ 0,00",
            "desconto": "R$ 0,00",
            "discount_products": "R$ 0,00",
            "discount_services": "R$ 0,00",
            "total_profit_product_value": "R$ 0,00",
            "total_profit_service_value": "R$ 0,00",
            "total_services_mechanic_cost_value": "R$ 0,00",
            "soma_markup_display": "0,00",
            "observations": "",
            "fixed_observation": "",
            "request": SimpleNamespace(user=SimpleNamespace(get_full_name=lambda: "Sistema")),
        }

        return render_to_string(template_name, context)

    def test_special_budget_label_renders_courtesy_in_every_budget_pdf(self) -> None:
        for template_name in self.templates:
            with self.subTest(template_name=template_name):
                html = self._render_pdf_template(template_name, BudgetType.COURTESY)

                self.assertIn("Orçamento de Cortesia", html)
                self.assertNotIn("Orçamento de Garantia", html)

                if template_name != "budget/partials/pdf/visualizarPDFMecanico.html":
                    self.assertIn("TOTAL A PAGAR:", html)

    def test_special_budget_label_renders_warranty_in_every_budget_pdf(self) -> None:
        for template_name in self.templates:
            with self.subTest(template_name=template_name):
                html = self._render_pdf_template(template_name, BudgetType.WARRANTY)

                self.assertIn("Orçamento de Garantia", html)
                self.assertNotIn("Orçamento de Cortesia", html)

                if template_name != "budget/partials/pdf/visualizarPDFMecanico.html":
                    self.assertIn("TOTAL A PAGAR:", html)

    def test_special_budget_label_is_hidden_for_sale_in_every_budget_pdf(self) -> None:
        for template_name in self.templates:
            with self.subTest(template_name=template_name):
                html = self._render_pdf_template(template_name, BudgetType.SALE)

                self.assertNotIn("Orçamento de Garantia", html)
                self.assertNotIn("Orçamento de Cortesia", html)
