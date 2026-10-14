from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.stock.models import StockTransfer
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class StockTransferScopingTests(TestCase):
    def setUp(self) -> None:
        self.account_a = Account.objects.create(name="Conta Transfer A")
        self.account_b = Account.objects.create(name="Conta Transfer B")

        self.user_a = User.objects.create_user(username="transfer-a", password="secret", cpf="12345678901")
        self.user_a.account = self.account_a
        self.user_a.is_account_owner = True
        self.user_a.save(update_fields=["account", "is_account_owner"])

        self.user_b = User.objects.create_user(username="transfer-b", password="secret", cpf="12345678902")
        self.user_b.account = self.account_b
        self.user_b.is_account_owner = True
        self.user_b.save(update_fields=["account", "is_account_owner"])

        self.workshop_a = Workshop.objects.create(
            account=self.account_a,
            name="Oficina Transfer A",
            cnpj="12.345.678/0001-90",
            phone="+5511999999991",
            address="Rua A, 1",
        )
        self.workshop_b = Workshop.objects.create(
            account=self.account_b,
            name="Oficina Transfer B",
            cnpj="12.345.678/0001-91",
            phone="+5511999999992",
            address="Rua B, 2",
        )
        role_a = WorkshopRole.objects.create(account=self.account_a, name="Diretor")
        role_b = WorkshopRole.objects.create(account=self.account_b, name="Diretor")
        WorkshopMember.objects.create(user=self.user_a, workshop=self.workshop_a, role=role_a, is_active=True)
        WorkshopMember.objects.create(user=self.user_b, workshop=self.workshop_b, role=role_b, is_active=True)

        self.foreign_transfer = StockTransfer.objects.create(
            operation_type=StockTransfer.OperationType.ADJUSTMENT,
            source_workshop=self.workshop_b,
            user=self.user_b,
            reason="motivo original",
        )
        self.own_transfer = StockTransfer.objects.create(
            operation_type=StockTransfer.OperationType.ADJUSTMENT,
            source_workshop=self.workshop_a,
            user=self.user_a,
            reason="motivo proprio",
        )

    def test_anonymous_cannot_update_transfer_reason(self) -> None:
        url = reverse("stock:update_transfer_reason", kwargs={"pk": self.foreign_transfer.pk})
        response = self.client.post(url, {"reason": "hack"})
        self.assertEqual(response.status_code, 302)
        self.foreign_transfer.refresh_from_db()
        self.assertEqual(self.foreign_transfer.reason, "motivo original")

    def test_user_cannot_update_other_account_transfer_reason(self) -> None:
        self.client.force_login(self.user_a)
        session = self.client.session
        session["active_workshop_id"] = self.workshop_a.pk
        session.save()

        url = reverse("stock:update_transfer_reason", kwargs={"pk": self.foreign_transfer.pk})
        response = self.client.post(url, {"reason": "hack"})
        self.assertEqual(response.status_code, 404)
        self.foreign_transfer.refresh_from_db()
        self.assertEqual(self.foreign_transfer.reason, "motivo original")

    def test_user_can_update_own_transfer_reason(self) -> None:
        self.client.force_login(self.user_a)
        session = self.client.session
        session["active_workshop_id"] = self.workshop_a.pk
        session.save()

        url = reverse("stock:update_transfer_reason", kwargs={"pk": self.own_transfer.pk})
        response = self.client.post(url, {"reason": "atualizado"})
        self.assertEqual(response.status_code, 204)
        self.own_transfer.refresh_from_db()
        self.assertEqual(self.own_transfer.reason, "atualizado")

    def test_transfer_update_view_hides_foreign_transfer(self) -> None:
        self.client.force_login(self.user_a)
        session = self.client.session
        session["active_workshop_id"] = self.workshop_a.pk
        session.save()

        url = reverse("stock:transfer_update", kwargs={"pk": self.foreign_transfer.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
