from __future__ import annotations

from datetime import timedelta

from django.test import RequestFactory, TestCase
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.views.kits import KitListView
from apps.catalog.views.products import ProductListView
from apps.catalog.views.services import ServiceListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Catalog {suffix}",
        cnpj=f"33.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class CatalogListViewFilterTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=1)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Teste")

    def test_product_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        active_product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="P-001",
            name="Produto Ativo",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            is_active=True,
        )
        inactive_product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="P-002",
            name="Produto Inativo",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            is_active=False,
        )

        default_view = ProductListView()
        default_view.request = self.factory.get("/catalog/products/")
        default_view.workshop = self.workshop
        default_queryset = default_view.get_queryset()

        inactive_view = ProductListView()
        inactive_view.request = self.factory.get("/catalog/products/", {"is_active": "0"})
        inactive_view.workshop = self.workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = ProductListView()
        all_view.request = self.factory.get("/catalog/products/", {"is_active": "all"})
        all_view.workshop = self.workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_product, default_queryset)
        self.assertNotIn(inactive_product, default_queryset)
        self.assertNotIn(active_product, inactive_queryset)
        self.assertIn(inactive_product, inactive_queryset)
        self.assertIn(active_product, all_queryset)
        self.assertIn(inactive_product, all_queryset)

    def test_service_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        active_service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Ativo",
            duration=timedelta(hours=1),
            selling_price=Money("20.00", "BRL"),
            is_active=True,
        )
        inactive_service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Inativo",
            duration=timedelta(hours=1),
            selling_price=Money("20.00", "BRL"),
            is_active=False,
        )

        default_view = ServiceListView()
        default_view.request = self.factory.get("/catalog/services/")
        default_view.workshop = self.workshop
        default_queryset = default_view.get_queryset()

        inactive_view = ServiceListView()
        inactive_view.request = self.factory.get("/catalog/services/", {"is_active": "0"})
        inactive_view.workshop = self.workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = ServiceListView()
        all_view.request = self.factory.get("/catalog/services/", {"is_active": "all"})
        all_view.workshop = self.workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_service, default_queryset)
        self.assertNotIn(inactive_service, default_queryset)
        self.assertNotIn(active_service, inactive_queryset)
        self.assertIn(inactive_service, inactive_queryset)
        self.assertIn(active_service, all_queryset)
        self.assertIn(inactive_service, all_queryset)

    def test_kit_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        active_kit = Kit.objects.create(workshop=self.workshop, name="Kit Ativo", is_active=True)
        inactive_kit = Kit.objects.create(workshop=self.workshop, name="Kit Inativo", is_active=False)

        default_view = KitListView()
        default_view.request = self.factory.get("/catalog/kits/")
        default_view.workshop = self.workshop
        default_queryset = default_view.get_queryset()

        inactive_view = KitListView()
        inactive_view.request = self.factory.get("/catalog/kits/", {"is_active": "0"})
        inactive_view.workshop = self.workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = KitListView()
        all_view.request = self.factory.get("/catalog/kits/", {"is_active": "all"})
        all_view.workshop = self.workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_kit, default_queryset)
        self.assertNotIn(inactive_kit, default_queryset)
        self.assertNotIn(active_kit, inactive_queryset)
        self.assertIn(inactive_kit, inactive_queryset)
        self.assertIn(active_kit, all_queryset)
        self.assertIn(inactive_kit, all_queryset)
