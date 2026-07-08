from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.workshops.context_processors import active_workshops
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import get_active_workshop_or_404


User = get_user_model()


class WorkshopRequestCachingTests(TestCase):
    def test_active_workshop_resolution_and_context_share_membership_query(self) -> None:
        user = User.objects.create_user(username="worker", password="secret", cpf="12345678901")
        account = Account.objects.create(name="Conta Teste")
        user.account = account
        user.save(update_fields=["account"])

        workshop = Workshop.objects.create(
            account=account,
            name="Oficina Cache",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        role = WorkshopRole.objects.create(account=account, name="Diretor")
        WorkshopMember.objects.create(user=user, workshop=workshop, role=role, is_active=True)

        request = RequestFactory().get("/")
        request.user = user
        request.session = {"active_workshop_id": workshop.pk}

        with self.assertNumQueries(1):
            resolved_workshop = get_active_workshop_or_404(request)
            payload = active_workshops(request)

        self.assertEqual(resolved_workshop, workshop)
        self.assertEqual(payload["active_workshop_id"], workshop.pk)
        self.assertTrue(payload["active_workshop_is_director"])
        self.assertFalse(payload["active_workshop_is_manager"])
        self.assertEqual(payload["active_workshops"], [workshop])
