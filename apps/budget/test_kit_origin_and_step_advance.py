from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.accounts.models import Account
from apps.budget.forms.shared import _render_budget_items_rows
from apps.budget.item_origin import AVULSO_ORIGIN_LABEL, build_kit_origin_indexes, numbered_kit_origin_label
from apps.budget.models import Budget, BudgetItem, BudgetKitItemOverride
from apps.budget.pdf_context import build_budget_pdf_context
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderKitItemOverride, WorkOrderStatus
from apps.workorder.util import _build_edit_items_context
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def _create_workshop_with_user(*, suffix: int) -> tuple[Workshop, User]:
    account = Account.objects.create(name=f"Conta Kits {suffix}")
    user = User.objects.create_user(username=f"kits-user-{suffix}", password="secret", cpf="52998224725")
    user.account = account
    user.save(update_fields=["account"])
    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Kits {suffix}",
        cnpj=f"12.345.678/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )
    role = WorkshopRole.objects.create(account=account, name="Diretor")
    WorkshopMember.objects.create(user=user, workshop=workshop, role=role, is_active=True)
    return workshop, user


class BudgetHtmxStepAdvanceTests(TestCase):
    def setUp(self) -> None:
        self.workshop, self.user = _create_workshop_with_user(suffix=1)
        today = timezone.localdate()
        WorkshopCost.objects.create(
            workshop=self.workshop,
            year=today.year,
            month=today.month,
            mechanic_quantity=1,
            work_days_per_month=22,
            minimum_hourly_cost=Money("80.00", "BRL"),
            hourly_cost_value=Money("160.00", "BRL"),
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 1),
            current_step=2,
            problem_description="Barulho no motor",
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_htmx_post_from_step_2_renders_step_3_without_collaborator_error(self) -> None:
        url = reverse("budget:budget_update", kwargs={"pk": self.budget.pk})
        response = self.client.post(
            f"{url}?step=2",
            data={"problem_description": "Barulho no motor", "notes": ""},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("Selecione pelo menos um colaborador para continuar.", content)
        self.assertIn("Diagnóstico Técnico", content)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.current_step, 3)
        self.assertIn("max_reached_step", response.context)
        self.assertEqual(response.context["max_reached_step"], 3)
        self.assertEqual(response.context["current_step"], 3)


class BudgetLocalizedPkNavigationTests(TestCase):
    def setUp(self) -> None:
        self.workshop, self.user = _create_workshop_with_user(suffix=40)
        today = timezone.localdate()
        WorkshopCost.objects.create(
            workshop=self.workshop,
            year=today.year,
            month=today.month,
            mechanic_quantity=1,
            work_days_per_month=22,
            minimum_hourly_cost=Money("80.00", "BRL"),
            hourly_cost_value=Money("160.00", "BRL"),
        )
        self.budget = Budget.objects.create(
            pk=1040,
            number=1040,
            workshop=self.workshop,
            entry_date=date(2026, 8, 1),
            current_step=2,
            problem_description="Barulho no motor",
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_create_flow_accepts_localized_thousand_separator_pk(self) -> None:
        url = reverse("budget:budget_create")
        response = self.client.get(
            f"{url}?step=1&pk=1.040",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"].pk, 1040)
        self.assertEqual(response.context["current_step"], 1)
        content = response.content.decode()
        self.assertIn("pk=1040", content)
        self.assertNotIn("pk=1.040", content)


class BudgetKitOriginDisplayTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Origem Kit",
            cnpj="11.222.333/0001-81",
            phone="+5511987654321",
            address="Rua Origem, 1",
            uf="SP",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Origem")
        self.product_avulso = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="AV-1",
            name="Filtro avulso",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        self.product_kit = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="KT-1",
            name="Filtro do kit",
            unit=Product.Unit.UND,
            cost_price=Money("5.00", "BRL"),
            selling_price=Money("15.00", "BRL"),
        )
        self.service_kit = Service.objects.create(
            workshop=self.workshop,
            name="Troca do kit",
            duration=timedelta(hours=1),
            suggested_cost=Money("50.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit revisão")
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 1), current_step=4)
        self.avulso_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=self.product_avulso,
            quantity=1,
        )
        self.kit_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            kit=self.kit,
            quantity=1,
        )
        BudgetKitItemOverride.objects.create(
            workshop=self.workshop,
            budget_item=self.kit_item,
            product=self.product_kit,
            quantity=2,
            product_cost_price=Money("5.00", "BRL"),
            product_selling_price=Money("15.00", "BRL"),
        )
        BudgetKitItemOverride.objects.create(
            workshop=self.workshop,
            budget_item=self.kit_item,
            service=self.service_kit,
            quantity=1,
            service_cost_price=Money("50.00", "BRL"),
            service_selling_price=Money("100.00", "BRL"),
            duration=timedelta(hours=1),
        )

    def test_origin_indexes_number_kits_sequentially(self) -> None:
        indexes = build_kit_origin_indexes([self.avulso_item, self.kit_item])
        self.assertEqual(indexes[self.kit_item.pk], 1)
        self.assertEqual(numbered_kit_origin_label(1), "Kit 1")

    def test_budget_rows_include_avulso_and_numbered_kit_tags(self) -> None:
        rows = _render_budget_items_rows(self.budget, step6=False)

        self.assertIn(AVULSO_ORIGIN_LABEL, rows["product"])
        self.assertIn("Kit 1", rows["product"])
        self.assertIn("Filtro do kit", rows["product"])
        self.assertIn("Filtro avulso", rows["product"])
        self.assertIn("Kit 1", rows["service"])
        self.assertIn("Troca do kit", rows["service"])
        self.assertIn("Kit revisão", rows["kit"])
        self.assertIn("Kit 1", rows["kit"])

    def test_pdf_context_has_no_kit_list_and_includes_components(self) -> None:
        context = build_budget_pdf_context(budget=self.budget, presentation="selected_items")

        self.assertEqual(context["kits"], [])
        product_names = [row["description"] for row in context["produtos"]]
        service_names = [row["description"] for row in context["servicos"]]
        self.assertIn("Filtro avulso", product_names)
        self.assertIn("Filtro do kit", product_names)
        self.assertIn("Troca do kit", service_names)
        for page in context["pages"]:
            self.assertEqual(page["kits"], [])


class WorkOrderKitOriginDisplayTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina OS Origem",
            cnpj="22.333.444/0001-55",
            phone="+5511987654321",
            address="Rua OS, 2",
            uf="SP",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo OS")
        self.product_avulso = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="OS-AV",
            name="Pastilha avulsa",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        self.product_kit = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="OS-KT",
            name="Pastilha do kit",
            unit=Product.Unit.UND,
            cost_price=Money("8.00", "BRL"),
            selling_price=Money("18.00", "BRL"),
        )
        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit freio")
        budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 1))
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=WorkOrderStatus.DRAFT,
        )
        self.avulso_item = WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            product=self.product_avulso,
            quantity=1,
        )
        self.kit_item = WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            kit=self.kit,
            quantity=1,
        )
        WorkOrderKitItemOverride.objects.create(
            workshop=self.workshop,
            workorder_item=self.kit_item,
            product=self.product_kit,
            quantity=1,
            product_cost_price=Money("8.00", "BRL"),
            product_selling_price=Money("18.00", "BRL"),
        )

    def test_display_items_include_avulso_and_kit_component_tags(self) -> None:
        context = _build_edit_items_context(self.workorder)
        display_products = list(context["display_product_items"])
        labels = [getattr(item, "origin_label", "") for item in display_products]
        names = [item.description for item in display_products]

        self.assertIn(AVULSO_ORIGIN_LABEL, labels)
        self.assertIn("Kit 1", labels)
        self.assertIn("Pastilha avulsa", names)
        self.assertIn("Pastilha do kit", names)
        self.assertEqual(len(context["kit_items"]), 1)
        self.assertEqual(len(context["product_items"]), 1)
