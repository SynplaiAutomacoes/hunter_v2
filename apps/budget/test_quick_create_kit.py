from __future__ import annotations

from datetime import date
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetItem
from apps.catalog.models.kits import Kit
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.customer.vehicle_engine import VehicleEngine
from apps.customer.vehicle_fuel import VehicleFuel
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class BudgetKitCatalogCreateRedirectTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Kit Cadastro")
        self.user = User.objects.create_user(username="kit-create-user", password="secret", cpf="12345678909")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Kit Cadastro",
            cnpj="12.345.678/0001-93",
            phone="+5511999999997",
            address="Rua Kit Cadastro, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Kit",
            cpf_or_cnpj="52998224725",
            email="kit@example.invalid",
        )
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="KTR1A23",
            brand="Toyota",
            model="Corolla",
            year_fabrication="2020",
            year_model="2021",
            color="Prata",
            engine=VehicleEngine.ENGINE_16,
            fuel=VehicleFuel.FLEX,
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 1),
            current_step=4,
            vehicle=self.vehicle,
        )
        self.budget_return_url = f"{reverse('budget:budget_update', kwargs={'pk': self.budget.pk})}?step=4"

    def test_kit_selection_modal_links_to_kit_create_with_budget_return(self) -> None:
        url = reverse("budget:item_selection", kwargs={"budget_id": self.budget.pk, "item_type": "kit"})
        response = self.client.get(url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cadastrar Kit")
        self.assertContains(response, reverse("catalog:kits_create"))
        self.assertContains(response, f"next={quote(self.budget_return_url, safe='/')}")
        self.assertContains(response, f"budget_id={self.budget.pk}")
        self.assertNotContains(response, "Cadastrar no Catálogo")
        self.assertNotContains(
            response,
            reverse("budget:quick_create_item", kwargs={"budget_id": self.budget.pk, "item_type": "kit"}),
        )
        self.assertNotContains(response, "Incluir Item Local")

    def test_kit_create_back_and_cancel_return_to_budget(self) -> None:
        url = reverse("catalog:kits_create")
        response = self.client.get(url, {"next": self.budget_return_url, "budget_id": str(self.budget.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{self.budget_return_url}"')
        self.assertContains(response, "Voltar")
        self.assertContains(response, "Cancelar")
        self.assertContains(response, f'name="next" value="{self.budget_return_url}"')
        self.assertContains(response, f'name="budget_id" value="{self.budget.pk}"')
        self.assertContains(response, f"budget_id={self.budget.pk}")

    def test_kit_create_without_next_keeps_kit_list_back_url(self) -> None:
        url = reverse("catalog:kits_create")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("catalog:kits_list"))

    def test_kit_create_save_redirects_to_budget(self) -> None:
        url = reverse("catalog:kits_create")
        response = self.client.post(
            url,
            data={"name": "Kit revisão 10 mil", "next": self.budget_return_url},
        )

        self.assertRedirects(response, self.budget_return_url, fetch_redirect_response=False)
        kit = Kit.objects.get(workshop=self.workshop, name="Kit revisão 10 mil")
        item = BudgetItem.objects.get(budget=self.budget, kit=kit)
        self.assertEqual(item.quantity, 1)
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.current_step, 4)

    def test_kit_create_save_adds_kit_to_source_budget(self) -> None:
        url = reverse("catalog:kits_create")
        response = self.client.post(
            url,
            data={
                "name": "Kit automático no orçamento",
                "next": self.budget_return_url,
                "budget_id": str(self.budget.pk),
            },
        )

        self.assertRedirects(response, self.budget_return_url, fetch_redirect_response=False)
        kit = Kit.objects.get(workshop=self.workshop, name="Kit automático no orçamento")
        item = BudgetItem.objects.get(budget=self.budget, kit=kit)
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.workshop_id, self.workshop.pk)

    def test_newly_created_kit_without_application_stays_visible(self) -> None:
        kit = Kit.objects.create(workshop=self.workshop, name="Kit sem aplicação")
        url = reverse("budget:item_selection", kwargs={"budget_id": self.budget.pk, "item_type": "kit"})
        response = self.client.get(url, {"newly_created_id": str(kit.pk)}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, kit.name)
        self.assertNotContains(response, 'data-hidden-by-kit-filter="true" style="display: none;"')
