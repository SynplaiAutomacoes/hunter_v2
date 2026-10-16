from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.collaborators.models import WorkshopMember
from apps.support_chat.application.session_resolver import SessionResolver
from apps.support_chat.models import ChatSession
from apps.workshops.models.workshops import Workshop


class SessionResolverTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Teste")
        self.user = User.objects.create(username="chatuser", account=self.account, cpf="12345678909")
        self.workshop = Workshop.objects.create(
            name="Oficina Teste",
            account=self.account,
            cnpj="11.222.333/0001-44",
            phone="+5511999999999",
            address="Rua Teste, 100",
        )
        self.member = WorkshopMember.objects.create(user=self.user, workshop=self.workshop, is_active=True)

    def test_creates_when_none(self) -> None:
        session = SessionResolver.resolve_active(member=self.member, workshop=self.workshop)
        self.assertTrue(session.is_active)
        self.assertEqual(ChatSession.objects.filter(member=self.member, workshop=self.workshop).count(), 1)

    def test_reuses_within_timeout(self) -> None:
        first = SessionResolver.resolve_active(member=self.member, workshop=self.workshop)
        second = SessionResolver.resolve_active(member=self.member, workshop=self.workshop)
        self.assertEqual(first.pk, second.pk)

    def test_creates_new_after_timeout(self) -> None:
        first = SessionResolver.resolve_active(member=self.member, workshop=self.workshop)
        first.last_interaction_at = timezone.now() - timedelta(minutes=6)
        first.save(update_fields=["last_interaction_at"])
        second = SessionResolver.resolve_active(member=self.member, workshop=self.workshop)
        self.assertNotEqual(first.pk, second.pk)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
