from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.workshops.models.oil_types import OilType
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class QuickOilTypeModalTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Oleo")
        self.user = User.objects.create_user(username="oil-user", password="secret", cpf="12345678901")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Oleo",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        role = WorkshopRole.objects.create(account=self.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_quick_create_renders_modal(self) -> None:
        response = self.client.get(reverse("workshops:oil_type_quick_create"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cadastro rápido de tipo de óleo")
        self.assertContains(response, "name")

    def test_quick_create_persists_and_triggers_event(self) -> None:
        url = reverse("workshops:oil_type_quick_create")
        response = self.client.post(
            url,
            data={
                "name": "Sintético 5W30",
                "validity_days": "180",
                "validity_km": "5000",
                "notification_lead_days": "7",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        oil_type = OilType.objects.get(workshop=self.workshop, name="Sintético 5W30")
        self.assertEqual(oil_type.validity_days, 180)
        self.assertEqual(oil_type.validity_km, 5000)
        self.assertTrue(oil_type.is_active)
        trigger = json.loads(response["HX-Trigger"])
        self.assertEqual(trigger["oilTypeSaved"]["id"], str(oil_type.pk))
        self.assertEqual(trigger["oilTypeSaved"]["name"], "Sintético 5W30")

    def test_quick_update_persists_and_triggers_event(self) -> None:
        oil_type = OilType.objects.create(
            workshop=self.workshop,
            name="Mineral 20W50",
            validity_days=90,
            validity_km=3000,
            notification_lead_days=5,
            is_active=False,
        )
        url = reverse("workshops:oil_type_quick_update", kwargs={"pk": oil_type.pk})
        response = self.client.post(
            url,
            data={
                "name": "Mineral 20W50 Plus",
                "validity_days": "120",
                "validity_km": "4000",
                "notification_lead_days": "10",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        oil_type.refresh_from_db()
        self.assertEqual(oil_type.name, "Mineral 20W50 Plus")
        self.assertEqual(oil_type.validity_days, 120)
        self.assertTrue(oil_type.is_active)
        trigger = json.loads(response["HX-Trigger"])
        self.assertEqual(trigger["oilTypeSaved"]["id"], str(oil_type.pk))
        self.assertEqual(trigger["oilTypeSaved"]["name"], "Mineral 20W50 Plus")
