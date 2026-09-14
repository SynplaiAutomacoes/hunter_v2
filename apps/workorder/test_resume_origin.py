from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.budget.item_origin import AVULSO_ORIGIN_LABEL, KIT_ORIGIN_LABEL
from apps.budget.models import Budget, BudgetItem
from apps.budget.review_totals import build_step6_table_totals
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
        kit_url = reverse("catalog:kits_update", kwargs={"pk": self.kit.pk})
        self.assertIn(f'href="{kit_url}"', kit_row.origin_badge)
        self.assertIn("<a ", kit_row.origin_badge)
        self.assertNotIn("<a ", avulso_row.origin_badge)

        self.assertEqual(len(service_rows), 1)
        service_row = service_rows[0]
        self.assertEqual(service_row.origin_label, KIT_ORIGIN_LABEL)
        self.assertEqual(service_row.service_id, self.kit_service.pk)
        self.assertIn(self.kit.name, service_row.origin_badge)
        self.assertIn(f'href="{kit_url}"', service_row.origin_badge)


class WorkOrderResumeDeduplicationTests(TestCase):
    """The resume must apply the same avulso-vs-kit and kit-vs-kit winner rule as the PDF."""

    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Dedup",
            cnpj="12.345.678/0001-95",
            phone="+5511999999995",
            address="Rua Dedup, 1",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Dedup")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="DP-1",
            name="Oleo Compartilhado",
            unit=Product.Unit.UND,
            cost_price=Money("15.00", "BRL"),
            selling_price=Money("30.00", "BRL"),
        )
        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Troca Compartilhada",
            duration=timedelta(hours=1),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("80.00", "BRL"),
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 24))
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)

    def _create_kit(self, *, name: str, product_quantity: int, service_quantity: int, service_duration: timedelta) -> Kit:
        kit = Kit.objects.create(workshop=self.workshop, name=name)
        kit.refresh_from_db()
        KitProduct.objects.create(kit=kit, product=self.product, quantity=product_quantity)
        KitService.objects.create(kit=kit, service=self.service, quantity=service_quantity, duration=service_duration)
        return kit

    def _add_kit_item(self, kit: Kit, *, quantity: int = 1) -> WorkOrderItem:
        return WorkOrderItem.objects.create(workshop=self.workshop, workorder=self.workorder, kit=kit, quantity=quantity)

    def _add_avulso_service_item(self, *, quantity: int) -> WorkOrderItem:
        return WorkOrderItem.objects.create(workshop=self.workshop, workorder=self.workorder, service=self.service, quantity=quantity)

    def _add_avulso_product_item(self, *, quantity: int) -> WorkOrderItem:
        return WorkOrderItem.objects.create(workshop=self.workshop, workorder=self.workorder, product=self.product, quantity=quantity)

    def _resume_rows(self) -> tuple[list, list]:
        context = _build_edit_items_context(self.workorder)
        return list(context["display_product_items"]), list(context["display_service_items"])

    def test_avulso_service_wins_over_kit_component_by_duration(self) -> None:
        self._add_avulso_service_item(quantity=2)
        self._add_kit_item(self._create_kit(name="Kit Menor", product_quantity=1, service_quantity=1, service_duration=timedelta(hours=1)))

        _product_rows, service_rows = self._resume_rows()

        self.assertEqual(len(service_rows), 1)
        self.assertEqual(service_rows[0].service_id, self.service.pk)
        self.assertEqual(service_rows[0].origin_label, AVULSO_ORIGIN_LABEL)
        self.assertEqual(service_rows[0].quantity, 2)

    def test_kit_component_wins_over_avulso_service_by_duration(self) -> None:
        self._add_avulso_service_item(quantity=1)
        kit = self._create_kit(name="Kit Maior", product_quantity=1, service_quantity=1, service_duration=timedelta(hours=3))
        self._add_kit_item(kit)

        _product_rows, service_rows = self._resume_rows()

        self.assertEqual(len(service_rows), 1)
        self.assertEqual(service_rows[0].service_id, self.service.pk)
        self.assertEqual(service_rows[0].origin_label, KIT_ORIGIN_LABEL)
        self.assertIn(kit.name, service_rows[0].origin_badge)

    def test_kit_product_wins_over_avulso_product_by_quantity(self) -> None:
        self._add_avulso_product_item(quantity=1)
        kit = self._create_kit(name="Kit Produto", product_quantity=4, service_quantity=1, service_duration=timedelta(hours=1))
        self._add_kit_item(kit)

        product_rows, _service_rows = self._resume_rows()

        self.assertEqual(len(product_rows), 1)
        self.assertEqual(product_rows[0].product_id, self.product.pk)
        self.assertEqual(product_rows[0].origin_label, KIT_ORIGIN_LABEL)
        self.assertEqual(product_rows[0].quantity, 4)

    def test_two_kits_sharing_components_keep_only_the_winning_kit(self) -> None:
        self._add_kit_item(self._create_kit(name="Kit Fraco", product_quantity=1, service_quantity=1, service_duration=timedelta(hours=1)))
        strong_kit = self._create_kit(name="Kit Forte", product_quantity=3, service_quantity=1, service_duration=timedelta(hours=4))
        self._add_kit_item(strong_kit)

        product_rows, service_rows = self._resume_rows()

        self.assertEqual(len(product_rows), 1)
        self.assertEqual(product_rows[0].quantity, 3)
        self.assertIn(strong_kit.name, product_rows[0].origin_badge)
        self.assertEqual(len(service_rows), 1)
        self.assertIn(strong_kit.name, service_rows[0].origin_badge)


class WorkOrderResumeStalePrefetchTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Prefetch",
            cnpj="12.345.678/0001-96",
            phone="+5511999999996",
            address="Rua Prefetch, 1",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Prefetch")
        self.kit_product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="KP-1",
            name="Produto Do Kit Prefetch",
            unit=Product.Unit.UND,
            cost_price=Money("15.00", "BRL"),
            selling_price=Money("30.00", "BRL"),
        )
        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit Prefetch")
        self.kit.refresh_from_db()
        KitProduct.objects.create(kit=self.kit, product=self.kit_product, quantity=1)
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 24))
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)

    def test_stale_prefetch_cache_still_expands_newly_added_kit(self) -> None:
        from apps.core.infrastructure.kit_prefetch import workorder_items_with_kit_prefetch

        stale_workorder = (
            WorkOrder.objects.filter(pk=self.workorder.pk)
            .prefetch_related(workorder_items_with_kit_prefetch(with_kit_tree=True))
            .get()
        )
        _ = list(stale_workorder.items.all())

        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            kit=self.kit,
            quantity=1,
        )

        context = _build_edit_items_context(stale_workorder)
        product_rows = list(context["display_product_items"])
        self.assertEqual(len(product_rows), 1)
        self.assertEqual(product_rows[0].origin_label, KIT_ORIGIN_LABEL)
        self.assertIn(self.kit.name, product_rows[0].origin_badge)

    def test_detail_prefetch_then_edit_context_does_not_duplicate_kit_overrides(self) -> None:
        """WorkOrderDetailView prefetches items with kit_overrides; edit context reloads items."""
        from apps.core.infrastructure.kit_prefetch import workorder_items_with_kit_prefetch

        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            kit=self.kit,
            quantity=1,
        )
        workorder = (
            WorkOrder.objects.filter(pk=self.workorder.pk)
            .prefetch_related(workorder_items_with_kit_prefetch(with_kit_tree=True))
            .get()
        )
        _ = list(workorder.items.all())

        context = _build_edit_items_context(workorder)
        product_rows = list(context["display_product_items"])
        self.assertEqual(len(product_rows), 1)
        self.assertEqual(product_rows[0].origin_label, KIT_ORIGIN_LABEL)


class WorkOrderAddKitBatchViewTests(TestCase):
    def setUp(self) -> None:
        from apps.accounts.models import Account
        from apps.collaborators.models import WorkshopMember
        from apps.iam.utils import get_or_create_director_role
        from django.contrib.auth import get_user_model

        User = get_user_model()
        account = Account.objects.create(name="Conta Kit Batch")
        self.user = User.objects.create_user(username="kit-batch-user", password="secret", cpf="39053344705")
        self.user.account = account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Kit Batch",
            cnpj="12.345.678/0001-97",
            phone="+5511999999997",
            address="Rua Kit Batch, 1",
        )
        role = get_or_create_director_role(account=account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Batch")
        self.kit_product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="KB-1",
            name="Oleo Batch Kit",
            unit=Product.Unit.UND,
            cost_price=Money("15.00", "BRL"),
            selling_price=Money("30.00", "BRL"),
        )
        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit Batch Revisao")
        self.kit.refresh_from_db()
        KitProduct.objects.create(kit=self.kit, product=self.kit_product, quantity=2)
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 24))
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_add_kit_batch_refreshes_resume_with_origin_badges(self) -> None:
        url = reverse("workorder:add_items_batch", kwargs={"pk": self.workorder.pk, "item_type": "kit"})
        response = self.client.post(url, data={"selected_items": [str(self.kit.pk)]})
        self.assertEqual(response.status_code, 200)
        self.assertIn(KIT_ORIGIN_LABEL, response.content.decode())
        self.assertIn(self.kit.name, response.content.decode())
        self.assertIn("resume-section", response.content.decode())

        context = _build_edit_items_context(self.workorder)
        product_rows = list(context["display_product_items"])
        self.assertEqual(len(product_rows), 1)
        self.assertEqual(product_rows[0].product_id, self.kit_product.pk)
        self.assertEqual(product_rows[0].quantity, 2)
        self.assertEqual(product_rows[0].origin_label, KIT_ORIGIN_LABEL)


class WorkOrderResumeGestorCostTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Custo Gestor",
            cnpj="12.345.678/0001-98",
            phone="+5511999999998",
            address="Rua Custo Gestor, 1",
        )
        self.labor = Service.objects.create(
            workshop=self.workshop,
            name="Kit embreagem OS",
            duration=timedelta(hours=8),
            suggested_cost=Money("10.00", "BRL"),
            selling_price=Money("600.00", "BRL"),
        )
        self.third_party = Service.objects.create(
            workshop=self.workshop,
            name="Retifica do Volante OS",
            duration=timedelta(0),
            suggested_cost=Money("150.00", "BRL"),
            selling_price=Money("360.00", "BRL"),
            is_third_party=True,
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 9, 14),
            slider=0,
            pricing_reference_month=9,
            pricing_reference_year=2026,
            pricing_hourly_cost_value=Money("164.35", "BRL"),
            pricing_working_hours_per_month=Decimal("176.00"),
            pricing_productive_salary_total=Money("4938.56", "BRL"),
            pricing_profitability_multiplier=Decimal("3.30"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=self.labor,
            quantity=1,
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=self.third_party,
            quantity=1,
        )
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            service=self.labor,
            quantity=1,
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            service=self.third_party,
            quantity=1,
        )

    def test_standalone_third_party_resume_matches_budget_table(self) -> None:
        table = build_step6_table_totals(budget=self.budget)
        context = _build_edit_items_context(self.workorder)
        third_party_row = next(row for row in context["display_service_items"] if row.service_id == self.third_party.pk)

        self.assertEqual(third_party_row.origin_label, AVULSO_ORIGIN_LABEL)
        self.assertEqual(third_party_row.gestor_cost_total, Money("0.00", "BRL"))
        self.assertEqual(context["resume_pdf"]["total_services_mechanic_cost_value"], table["services"].cost)
        self.assertEqual(context["resume_pdf"]["total_profit_service_value"], table["services"].profit)

    def test_kit_third_party_resume_keeps_catalog_cost(self) -> None:
        kit = Kit.objects.create(workshop=self.workshop, name="Kit terceiro")
        kit.refresh_from_db()
        KitService.objects.create(
            kit=kit,
            service=self.third_party,
            quantity=1,
            duration=timedelta(0),
            cost_price=Money("150.00", "BRL"),
            selling_price=Money("360.00", "BRL"),
        )
        kit_workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=kit_workorder,
            kit=kit,
            quantity=1,
        )

        context = _build_edit_items_context(kit_workorder)
        service_rows = list(context["display_service_items"])
        self.assertEqual(len(service_rows), 1)
        self.assertEqual(service_rows[0].origin_label, KIT_ORIGIN_LABEL)
        self.assertEqual(service_rows[0].gestor_cost_total, Money("150.00", "BRL"))
