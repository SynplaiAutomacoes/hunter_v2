from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.budget.forms import BudgetStep1Form
from apps.budget.services.entry_km import BUDGET_KM_BELOW_CADASTRO_MESSAGE, budget_entry_km_is_below_cadastro
from apps.budget.views.workflow_views import _parse_budget_pk
from apps.customer.models import Customer, Vehicle
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class BudgetEntryKmRuleTests(SimpleTestCase):
    def test_higher_entry_km_is_not_below_cadastro(self) -> None:
        self.assertFalse(budget_entry_km_is_below_cadastro(current_km=100_000, registered_km=87_673))

    def test_lower_entry_km_is_below_cadastro(self) -> None:
        self.assertTrue(budget_entry_km_is_below_cadastro(current_km=10, registered_km=87_673))

    def test_match_allows_progress(self) -> None:
        self.assertFalse(budget_entry_km_is_below_cadastro(current_km=87_673, registered_km=87_673))

    def test_missing_cadastro_km_does_not_block(self) -> None:
        self.assertFalse(budget_entry_km_is_below_cadastro(current_km=100_000, registered_km=None))


class BudgetPkQueryParsingTests(SimpleTestCase):
    def test_parses_localized_thousand_separator_pk(self) -> None:
        self.assertEqual(_parse_budget_pk("1.155"), 1155)

    def test_parses_plain_numeric_pk(self) -> None:
        self.assertEqual(_parse_budget_pk("1155"), 1155)

    def test_empty_pk_is_none(self) -> None:
        self.assertIsNone(_parse_budget_pk(""))
        self.assertIsNone(_parse_budget_pk(None))


class BudgetStep1EntryKmFormTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina KM Entrada",
            cnpj="12.345.678/0001-91",
            phone="+5511999999999",
            address="Rua KM, 2",
            uf="SP",
        )
        self.user = User.objects.create_user(username="orcamentista-km", password="senha123", cpf="12345678909")
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente KM Entrada",
            cpf_or_cnpj="52998224725",
            email="km-entrada@example.invalid",
        )
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="QRW3D41",
            brand="Jeep",
            model="Renegade",
            year_fabrication="2019",
            year_model="2020",
            color="Branco",
            km=87_673,
        )
        self.request = RequestFactory().post("/budget/create/")
        self.request.user = self.user

    def _form(self, *, current_km: str) -> BudgetStep1Form:
        data = {
            "entry_date": "17/08/2026",
            "budget_type": "sale",
            "customer": str(self.customer.pk),
            "vehicle": str(self.vehicle.pk),
            "current_km": current_km,
        }
        return BudgetStep1Form(
            data=data,
            workshop=self.workshop,
            request=self.request,
        )

    def test_higher_km_than_cadastro_allows_step(self) -> None:
        form = self._form(current_km="100000")
        self.assertTrue(form.is_valid(), form.errors)

    def test_lower_km_than_cadastro_blocks_step(self) -> None:
        form = self._form(current_km="10")
        self.assertFalse(form.is_valid())
        self.assertIn(BUDGET_KM_BELOW_CADASTRO_MESSAGE, form.errors["current_km"])

    def test_matching_cadastro_km_is_valid(self) -> None:
        form = self._form(current_km="87673")
        self.assertTrue(form.is_valid(), form.errors)

    def test_vehicle_from_another_customer_is_rejected(self) -> None:
        other_customer = Customer.objects.create(
            workshop=self.workshop,
            name="Outro Cliente",
            cpf_or_cnpj="11144477735",
            email="outro-cliente@example.invalid",
        )
        other_vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=other_customer,
            plate="ABC1D23",
            brand="Fiat",
            model="Uno",
            year_fabrication="2015",
            year_model="2016",
            color="Prata",
            km=50_000,
        )
        form = BudgetStep1Form(
            data={
                "entry_date": "17/08/2026",
                "budget_type": "sale",
                "customer": str(self.customer.pk),
                "vehicle": str(other_vehicle.pk),
                "current_km": "50000",
            },
            workshop=self.workshop,
            request=self.request,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("vehicle", form.errors)
