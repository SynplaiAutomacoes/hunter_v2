from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.workshops import can_view_payroll_details, is_workshop_director, is_workshop_manager


User = get_user_model()


class PayrollPermissionTests(TestCase):
    def _create_account_with_workshop(self, *, suffix: int) -> tuple[Account, Workshop]:
        account = Account.objects.create(name=f"Conta {suffix}")
        workshop = Workshop.objects.create(
            account=account,
            name=f"Oficina {suffix}",
            cnpj=f"61.222.333/0001-{suffix:02d}",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )
        return account, workshop

    def _create_user(self, *, account: Account, suffix: int, is_account_owner: bool = False):
        return User.objects.create_user(
            username=f"user_{suffix}",
            password="senha123",
            cpf=f"123456789{suffix:02d}",
            account=account,
            is_account_owner=is_account_owner,
        )

    def test_manager_needs_explicit_payroll_permission(self) -> None:
        account, workshop = self._create_account_with_workshop(suffix=31)
        user = self._create_user(account=account, suffix=31)
        manager_role = WorkshopRole.objects.create(account=account, name="Gerente")
        WorkshopMember.objects.create(user=user, workshop=workshop, role=manager_role, is_active=True)

        self.assertTrue(is_workshop_manager(user=user, workshop=workshop))
        self.assertFalse(can_view_payroll_details(user=user, workshop=workshop))

    def test_director_keeps_payroll_permission_bypass(self) -> None:
        account, workshop = self._create_account_with_workshop(suffix=32)
        user = self._create_user(account=account, suffix=32)
        director_role = WorkshopRole.objects.create(account=account, name="Diretor")
        WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)

        self.assertTrue(is_workshop_director(user=user, workshop=workshop))
        self.assertTrue(can_view_payroll_details(user=user, workshop=workshop))
