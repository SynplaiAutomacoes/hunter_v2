from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.utils import DataError
from django.test import RequestFactory, TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.budget.views.item_views import AddItemsBatchToBudgetView
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def _create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Description {suffix}",
        cnpj=f"44.555.666/0001-{suffix:02d}",
        phone="+5511987654321",
        address=f"Rua Description, {suffix}",
        uf="SP",
    )


class BudgetItemDescriptionLengthTests(TestCase):
    def setUp(self) -> None:
        self.workshop = _create_workshop(suffix=1)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Description")
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 1))

    def test_budget_item_copies_product_name_longer_than_100_chars(self) -> None:
        long_name = "P" * 150
        product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="P-LONG",
            name=long_name,
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )

        item = BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, product=product, quantity=1)

        self.assertEqual(item.description, long_name)
        self.assertEqual(len(item.description), 150)

    def test_budget_item_copies_service_name_longer_than_100_chars(self) -> None:
        long_name = "S" * 200
        service = Service.objects.create(
            workshop=self.workshop,
            name=long_name,
            duration=timedelta(hours=1),
            selling_price=Money("50.00", "BRL"),
        )

        item = BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, service=service, quantity=1)

        self.assertEqual(item.description, long_name)
        self.assertEqual(len(item.description), 200)


class AddItemsBatchDescriptionErrorTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = _create_workshop(suffix=2)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Batch")
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 1))
        self.user = User.objects.create_user(username="budget-desc-user", password="test-pass")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="P-BATCH",
            name="Produto Batch",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )

    def test_batch_add_shows_specific_modal_for_description_too_long(self) -> None:
        request = self.factory.post(
            f"/budget/{self.budget.pk}/add-items-batch/product/",
            {"selected_items": [str(self.product.pk)]},
        )
        request.user = self.user
        request.session = self.client.session

        view = AddItemsBatchToBudgetView()
        view.setup(request, budget_id=self.budget.pk, item_type="product")
        view.workshop = self.workshop

        with patch.object(
            BudgetItem.objects,
            "get_or_create",
            side_effect=DataError("value too long for type character varying(500)"),
        ):
            response = view.post(request, budget_id=self.budget.pk, item_type="product")

        content = response.content.decode()
        self.assertIn("Nome muito longo", content)
        self.assertIn("excede o tamanho máximo", content)
        self.assertNotIn("Tente novamente em instantes", content)
