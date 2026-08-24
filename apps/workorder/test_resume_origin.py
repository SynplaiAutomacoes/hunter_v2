from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from djmoney.money import Money

from apps.budget.item_origin import AVULSO_ORIGIN_LABEL, KIT_ORIGIN_LABEL
from apps.budget.models import Budget
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workorder.models import WorkOrder, WorkOrderItem
from apps.workorder.util import _build_edit_items_context
from apps.workshops.models.workshops import Workshop


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "workorder" / "partials"


class WorkOrderResumeOriginTemplateTests(SimpleTestCase):
    def test_resume_renders_origin_badge(self) -> None:
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")
        self.assertEqual(resume.count("item.origin_badge|safe"), 2)


class WorkOrderResumeKitExpansionTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Origem Kit",
            cnpj="12.345.678/0001-94",
            phone="+5511999999994",
            address="Rua Origem, 1",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Origem")
        self.avulso_product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="AV-1",
            name="Filtro Avulso",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        self.kit_product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="KT-1",
            name="Oleo Do Kit",
            unit=Product.Unit.UND,
            cost_price=Money("15.00", "BRL"),
            selling_price=Money("30.00", "BRL"),
        )
        self.kit_service = Service.objects.create(
            workshop=self.workshop,
            name="Troca Do Kit",
            duration=timedelta(hours=1),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("80.00", "BRL"),
        )
        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit Revisao 10k")
        self.kit.refresh_from_db()
        KitProduct.objects.create(kit=self.kit, product=self.kit_product, quantity=2)
        KitService.objects.create(kit=self.kit, service=self.kit_service, quantity=1, duration=timedelta(hours=1))
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 24))
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            product=self.avulso_product,
            quantity=1,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("20.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            kit=self.kit,
            quantity=1,
        )

    def test_resume_expands_kit_components_with_origin_badges(self) -> None:
        context = _build_edit_items_context(self.workorder)
        product_rows = list(context["display_product_items"])
        service_rows = list(context["display_service_items"])

        self.assertEqual(len(product_rows), 2)
        avulso_row = next(row for row in product_rows if row.origin_label == AVULSO_ORIGIN_LABEL)
        kit_row = next(row for row in product_rows if row.origin_label == KIT_ORIGIN_LABEL)
        self.assertEqual(avulso_row.product_id, self.avulso_product.pk)
        self.assertEqual(kit_row.product_id, self.kit_product.pk)
        self.assertEqual(kit_row.quantity, 2)
        self.assertIn(KIT_ORIGIN_LABEL, kit_row.origin_badge)
        self.assertIn(AVULSO_ORIGIN_LABEL, avulso_row.origin_badge)
        self.assertIn(self.kit.name, kit_row.origin_badge)

        self.assertEqual(len(service_rows), 1)
        service_row = service_rows[0]
        self.assertEqual(service_row.origin_label, KIT_ORIGIN_LABEL)
        self.assertEqual(service_row.service_id, self.kit_service.pk)
        self.assertIn(self.kit.name, service_row.origin_badge)
