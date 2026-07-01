from __future__ import annotations

import json
from datetime import date

from django.test import RequestFactory, TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetItemBenefitType
from apps.budget.views.item_views import BudgetItemUpdateView
from apps.budget.views.local_item_views import CreateLocalItemView
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Budget Item {suffix}",
        cnpj=f"44.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class BudgetItemModalFlowTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop()
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Peças")
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 6, 30), current_step=4)

    def _post_item_update(self, item: BudgetItem, data: dict[str, str]) -> object:
        request = self.factory.post(f"/budget/{self.budget.pk}/item/{item.pk}/edit/", data=data, HTTP_HX_REQUEST="true")
        request.session = self.client.session
        view = BudgetItemUpdateView()
        view.workshop = self.workshop
        return view.post(request, self.budget.pk, item.pk)

    def test_save_only_updates_budget_item_without_changing_catalog_product(self) -> None:
        product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="P-001",
            name="Filtro original",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        item = BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, product=product, quantity=1)

        response = self._post_item_update(
            item,
            {
                "action": "save_only",
                "description": "Filtro alterado no orçamento",
                "quantity": "2",
                "product_cost_price_0": "11.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "25.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "3.00",
                "shipping_1": "BRL",
                "ncm": "",
                "item_benefit_type": BudgetItemBenefitType.NORMAL,
            },
        )

        item.refresh_from_db()
        product.refresh_from_db()

        self.assertEqual(item.description, "Filtro alterado no orçamento")
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.product_selling_price, Money("25.00", "BRL"))
        self.assertEqual(product.name, "Filtro original")
        self.assertEqual(product.selling_price, Money("20.00", "BRL"))
        self.assertIn('id="product-list-body"', response.content.decode())
        self.assertIn("hx-swap-oob", response.content.decode())
        self.assertIn("HX-Trigger-After-Swap", response.headers)

    def test_update_master_updates_catalog_product_after_budget_item_save(self) -> None:
        product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="P-002",
            name="Pastilha original",
            unit=Product.Unit.UND,
            cost_price=Money("30.00", "BRL"),
            selling_price=Money("60.00", "BRL"),
        )
        item = BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, product=product, quantity=1)

        self._post_item_update(
            item,
            {
                "action": "update_master",
                "description": "Pastilha atualizada",
                "quantity": "1",
                "product_cost_price_0": "35.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "70.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "ncm": "87089990",
                "item_benefit_type": BudgetItemBenefitType.NORMAL,
            },
        )

        product.refresh_from_db()

        self.assertEqual(product.name, "Pastilha atualizada")
        self.assertEqual(product.cost_price, Money("35.00", "BRL"))
        self.assertEqual(product.selling_price, Money("70.00", "BRL"))
        self.assertEqual(product.ncm, "87089990")

    def test_child_local_product_creation_updates_main_product_table_and_closes_parent_modal(self) -> None:
        request = self.factory.post(
            f"/budget/{self.budget.pk}/create-local/product/",
            data={
                "modal_context": "child",
                "description": "Produto local",
                "quantity": "1",
                "product_cost_price_0": "8.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "15.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "item_benefit_type": BudgetItemBenefitType.NORMAL,
            },
            HTTP_HX_REQUEST="true",
        )
        request.session = self.client.session
        view = CreateLocalItemView()
        view.workshop = self.workshop

        response = view.post(request, self.budget.pk, "product")

        item = BudgetItem.objects.get(budget=self.budget, description="Produto local")
        triggers = json.loads(response.headers["HX-Trigger-After-Swap"])

        self.assertTrue(item.is_local)
        self.assertEqual(item.local_item_type, "product")
        self.assertIsNone(item.product_id)
        self.assertEqual(response.headers["HX-Retarget"], "#product-list-body")
        self.assertIn("Produto local", response.content.decode())
        self.assertTrue(triggers["closeModal"])
        self.assertTrue(triggers["closeParentBudgetModal"])

    def test_zero_value_local_product_still_renders_in_product_table(self) -> None:
        request = self.factory.post(
            f"/budget/{self.budget.pk}/create-local/product/",
            data={
                "description": "Produto local zerado",
                "quantity": "1",
                "product_cost_price_0": "0.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "0.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "item_benefit_type": BudgetItemBenefitType.NORMAL,
            },
            HTTP_HX_REQUEST="true",
        )
        request.session = self.client.session
        view = CreateLocalItemView()
        view.workshop = self.workshop

        response = view.post(request, self.budget.pk, "product")

        item = BudgetItem.objects.get(budget=self.budget, description="Produto local zerado")
        response_html = response.content.decode()

        self.assertEqual(item.local_item_type, "product")
        self.assertEqual(response.headers["HX-Retarget"], "#product-list-body")
        self.assertIn("Produto local zerado", response_html)
        self.assertNotIn("Nenhum produto adicionado", response_html)
