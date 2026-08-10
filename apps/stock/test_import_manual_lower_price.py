from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.stock.forms import ImportManualItemsForm, ManualLinkItemEditForm
from apps.stock.models import StockImport
from apps.workshops.models.workshops import Workshop


class ImportManualItemsLowerPriceTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Import Lower Price",
            cnpj="66.777.888/0001-01",
            phone="+5511999999999",
            address="Rua Teste, 789",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Import")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="COXIM-1",
            name="Coxim do cambio inferior",
            unit=Product.Unit.UND,
            cost_price=Money("93.60", "BRL"),
            selling_price=Money("202.78", "BRL"),
            last_used_price=Money("2985.89", "BRL"),
        )
        self.stock_import = StockImport.objects.create(
            workshop=self.workshop,
            nf_key="0" * 44,
            method=StockImport.ImportMethods.MANUAL,
            items_data=[
                {
                    "linked_product_id": str(self.product.pk),
                    "qtd": "1",
                    "valor": "93.60",
                    "selling_price": "202.78",
                }
            ],
        )

    def _build_form(self, *, data: dict[str, str] | None = None) -> ImportManualItemsForm:
        return ImportManualItemsForm(
            data=data,
            instance=self.stock_import,
            workshop=self.workshop,
        )

    def test_clean_blocks_lower_selling_price_without_confirmation(self) -> None:
        form = self._build_form(data={})

        self.assertFalse(form.is_valid())
        self.assertTrue(any("Último valor usado" in error for error in form.non_field_errors()))

    def test_clean_allows_lower_selling_price_with_confirmation(self) -> None:
        form = self._build_form(data={"confirm_lower_price": "1"})

        self.assertTrue(form.is_valid(), form.errors)

    def test_clean_allows_lower_selling_price_with_confirm_button(self) -> None:
        form = self._build_form(data={"confirm_lower_price_btn": "1"})

        self.assertTrue(form.is_valid(), form.errors)

    def test_clean_allows_item_level_lower_price_confirmation(self) -> None:
        self.stock_import.items_data = [
            {
                "linked_product_id": str(self.product.pk),
                "qtd": "1",
                "valor": "93.60",
                "selling_price": "202.78",
                "lower_price_confirmed": True,
                "lower_price_confirmed_selling_price": "202.78",
            }
        ]
        self.stock_import.save(update_fields=["items_data"])

        form = self._build_form(data={})

        self.assertTrue(form.is_valid(), form.errors)

    def test_manual_link_editor_persists_lower_price_confirmation(self) -> None:
        form = ManualLinkItemEditForm(
            data={
                "product_id": str(self.product.pk),
                "item_idx": "0",
                "quantity": "1",
                "unit_cost_0": "93.60",
                "unit_cost_1": "BRL",
                "selling_price_0": "202.78",
                "selling_price_1": "BRL",
                "confirm_lower_price": "1",
            },
            product=self.product,
            stock_import=self.stock_import,
            item_idx=0,
        )

        self.assertTrue(form.is_valid(), form.errors)
        item_data = form.build_item_data(existing_item=self.stock_import.items_data[0])
        self.assertTrue(item_data["lower_price_confirmed"])
        self.assertEqual(item_data["lower_price_confirmed_selling_price"], "202.78")
        self.assertEqual(Decimal(item_data["selling_price"]), Decimal("202.78"))

    def test_manual_table_html_exposes_price_row_data_attributes(self) -> None:
        form = self._build_form()
        html = form._generate_manual_table_html()

        self.assertIn('class="js-manual-price-row', html)
        self.assertIn('data-product-name="Coxim do cambio inferior"', html)
        self.assertIn('data-selling-price="202.78"', html)
        self.assertIn('data-last-used-price="2985.89"', html)

    def test_warning_layout_includes_continue_button(self) -> None:
        form = self._build_form(data={})
        self.assertFalse(form.is_valid())

        warning_html = ""
        for field in form.helper.layout.fields[0].fields:
            html = getattr(field, "html", "")
            if "confirm_lower_price_btn" in html:
                warning_html = html
                break

        self.assertIn('name="confirm_lower_price_btn"', warning_html)
        self.assertIn("Continuar mesmo assim", warning_html)
