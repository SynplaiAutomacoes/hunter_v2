from __future__ import annotations

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from djmoney.money import Money

from apps.workorder.pdf_context import WorkOrderPdfBudgetProxy


class BudgetAndWorkOrderPdfKmDisplayTests(SimpleTestCase):
    def _base_page(self) -> dict[str, object]:
        return {
            "produtos": [],
            "servicos": [],
            "page_number": 1,
            "total_pages": 1,
        }

    def test_budget_pdf_shows_entry_km_only(self) -> None:
        budget = SimpleNamespace(
            number=101,
            current_km=45230,
            workshop=SimpleNamespace(
                pdf_name="Oficina Teste",
                cnpj="12345678000199",
                address="Rua A, 1",
                pdf_phone="11999999999",
            ),
            customer=SimpleNamespace(
                name="Cliente",
                cpf_or_cnpj="12345678901",
                phone="11988887777",
                logradouro="Rua B",
                numero="10",
                bairro="Centro",
                cidade="São Paulo",
                cep="01000-000",
            ),
            vehicle=SimpleNamespace(
                plate="ABC1D23",
                year_model=2020,
                year_fabrication=2019,
                brand="Fiat",
                model="Argo",
                engine="1.0",
                fuel="Flex",
                color="Prata",
            ),
            problem_description="Barulho",
            customer_agreed_departure_at=None,
        )
        html = render_to_string(
            "budget/partials/pdf/visualizarPDF.html",
            {
                "budget": budget,
                "pages": [self._base_page()],
                "total_produtos": Money(0, "BRL"),
                "total_servicos": Money(0, "BRL"),
                "desconto": Money(0, "BRL"),
                "discount_products": Money(0, "BRL"),
                "discount_services": Money(0, "BRL"),
                "discount_type": "both",
                "total_geral": Money(0, "BRL"),
                "payments": [],
                "observations": "",
                "fixed_observation": "",
                "workshop_logo_data_uri": "",
            },
        )

        self.assertIn("Km-E:", html)
        self.assertIn("45.230", html)
        self.assertNotIn("Km-S:", html)

    def test_workorder_pdf_shows_entry_and_exit_km(self) -> None:
        customer = SimpleNamespace(
            name="Cliente",
            cpf_or_cnpj="12345678901",
            phone="11988887777",
            logradouro="Rua B",
            numero="10",
            bairro="Centro",
            cidade="São Paulo",
            cep="01000-000",
        )
        vehicle = SimpleNamespace(
            plate="ABC1D23",
            year_model=2020,
            year_fabrication=2019,
            brand="Fiat",
            model="Argo",
            engine="1.0",
            fuel="Flex",
            color="Prata",
        )
        workshop = SimpleNamespace(
            pdf_name="Oficina Teste",
            cnpj="12345678000199",
            address="Rua A, 1",
            pdf_phone="11999999999",
        )
        budget = WorkOrderPdfBudgetProxy(
            id=55,
            number=55,
            workshop=workshop,
            created=None,
            criado_em=None,
            customer=customer,
            vehicle=vehicle,
            problem_description="Barulho",
            observations="",
            fixed_observation="",
            resolved_discount_value=Money(0, "BRL"),
            total_budget_value=Money(0, "BRL"),
            budget_status="Entregue",
            delivered_at=None,
            customer_agreed_departure_at=None,
            current_km=45230,
        )
        workorder = SimpleNamespace(delivered_at=None, km_final=45310)
        html = render_to_string(
            "budget/partials/pdf/visualizarPDF.html",
            {
                "budget": budget,
                "workorder": workorder,
                "pages": [self._base_page()],
                "total_produtos": Money(0, "BRL"),
                "total_servicos": Money(0, "BRL"),
                "desconto": Money(0, "BRL"),
                "discount_products": Money(0, "BRL"),
                "discount_services": Money(0, "BRL"),
                "discount_type": "both",
                "total_geral": Money(0, "BRL"),
                "payments": [],
                "observations": "",
                "fixed_observation": "",
                "workshop_logo_data_uri": "",
            },
        )

        self.assertIn("Km-E:", html)
        self.assertIn("45.230", html)
        self.assertIn("Km-S:", html)
        self.assertIn("45.310", html)
