from __future__ import annotations

from apps.accounts.models import Account, User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.views.monthly_costs import MonthlyCostListView


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"workshop-filter-director{suffix}", password="123", cpf=f"33344455{suffix:03d}")
    account = Account.objects.create(name=f"Conta Workshop Filter {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Filter {suffix}",
        cnpj=f"36.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
        uf="SP",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)
    return user, workshop


class WorkshopListViewFilterTests(TestCase):
    def test_workshop_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=1)
        self.client.force_login(user)
        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()

        director_role = WorkshopMember.objects.get(user=user, workshop=workshop).role
        inactive_workshop = Workshop.objects.create(
            account=workshop.account,
            name="Oficina Inativa",
            cnpj="36.222.333/0001-99",
            phone="+5511888888888",
            address="Rua Inativa, 999",
            uf="SP",
            is_active=False,
        )
        WorkshopMember.objects.create(user=user, workshop=inactive_workshop, role=director_role, is_active=True)

        default_response = self.client.get(reverse("workshops:list"))
        inactive_response = self.client.get(reverse("workshops:list"), {"is_active": "0"})
        all_response = self.client.get(reverse("workshops:list"), {"is_active": "all"})

        default_names = [item.name for item in default_response.context["workshops"]]
        inactive_names = [item.name for item in inactive_response.context["workshops"]]
        all_names = [item.name for item in all_response.context["workshops"]]

        self.assertContains(default_response, 'name="is_active"', html=False)
        self.assertContains(default_response, 'value="all"', html=False)
        self.assertIn(workshop.name, default_names)
        self.assertNotIn(inactive_workshop.name, default_names)
        self.assertNotIn(workshop.name, inactive_names)
        self.assertIn(inactive_workshop.name, inactive_names)
        self.assertIn(workshop.name, all_names)
        self.assertIn(inactive_workshop.name, all_names)


class MonthlyCostListViewFilterTests(TestCase):
    def test_monthly_cost_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=2)
        active_cost = MonthlyCost.objects.create(workshop=workshop, name="Custo ativo", is_active=True)
        inactive_cost = MonthlyCost.objects.create(workshop=workshop, name="Custo inativo", is_active=False)
        factory = RequestFactory()

        default_view = MonthlyCostListView()
        default_view.request = factory.get("/workshops/costs/")
        default_view.workshop = workshop
        default_queryset = default_view.get_queryset()

        inactive_view = MonthlyCostListView()
        inactive_view.request = factory.get("/workshops/costs/", {"is_active": "0"})
        inactive_view.workshop = workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = MonthlyCostListView()
        all_view.request = factory.get("/workshops/costs/", {"is_active": "all"})
        all_view.workshop = workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_cost, default_queryset)
        self.assertNotIn(inactive_cost, default_queryset)
        self.assertNotIn(active_cost, inactive_queryset)
        self.assertIn(inactive_cost, inactive_queryset)
        self.assertIn(active_cost, all_queryset)
        self.assertIn(inactive_cost, all_queryset)
