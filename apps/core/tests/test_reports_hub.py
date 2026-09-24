from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.core.infrastructure.services.management_reports import REPORT_KEYS, group_catalog_by_category
from apps.core.presentation.management_report_views import ReportsHubView
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def create_workshop_with_member(*, suffix: int) -> tuple[Workshop, User]:
    account = Account.objects.create(name=f"Conta Hub {suffix}")
    user = User.objects.create_user(username=f"hub-user-{suffix}", password="secret", cpf="39053344705")
    user.account = account
    user.save(update_fields=["account"])
    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Hub {suffix}",
        cnpj=f"22.333.444/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Hub, 100",
    )
    role = get_or_create_director_role(account=account)
    WorkshopMember.objects.create(workshop=workshop, user=user, role=role, is_active=True)
    return workshop, user


class ReportsHubTests(TestCase):
    def test_reports_hub_url_resolves(self) -> None:
        self.assertEqual(reverse("core:reports_hub"), "/core/reports/")

    def test_catalog_covers_all_planned_reports(self) -> None:
        groups = group_catalog_by_category()
        self.assertEqual(len(groups), 5)
        all_keys = {entry.key for group in groups for entry in group["entries"]}  # type: ignore[index]
        self.assertTrue({"rentabilidade_acumulada", "curva_abc", "top_clientes", "top_mecanicos", "clientes"} <= all_keys)
        self.assertGreaterEqual(len(REPORT_KEYS), 20)

    def test_reports_hub_view_renders_sections(self) -> None:
        workshop, user = create_workshop_with_member(suffix=1)
        request = RequestFactory().get(reverse("core:reports_hub"))
        request.user = user
        request.session = self.client.session
        request.session["active_workshop_id"] = workshop.pk
        request.session.save()

        view = ReportsHubView()
        view.request = request
        view.workshop = workshop
        view.kwargs = {}
        context = view.get_context_data()

        self.assertEqual(len(context["report_groups"]), 5)
