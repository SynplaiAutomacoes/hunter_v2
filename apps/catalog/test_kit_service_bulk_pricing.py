from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.accounts.models import Account
from apps.catalog.models.kits import Kit
from apps.catalog.models.services import Service
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class KitServiceBulkPricingViewTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Bulk Pricing")
        self.user = User.objects.create_user(username="bulk-pricing-user", password="secret", cpf="39053344705")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Bulk Pricing",
            cnpj="12.345.678/0001-91",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )
        role = WorkshopRole.objects.create(account=self.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Troca de óleo",
            duration=timedelta(hours=1),
            suggested_cost=Money("50.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        today = timezone.localdate()
        self.workshop_cost = WorkshopCost.objects.create(
            workshop=self.workshop,
            year=today.year,
            month=today.month,
            mechanic_quantity=1,
            work_days_per_month=22,
            minimum_hourly_cost=Money("80.00", "BRL"),
            hourly_cost_value=Money("160.00", "BRL"),
        )
        self.url = reverse("catalog:kits_service_bulk_pricing")

    def _post(self, payload: dict[str, object]):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_success_returns_cost_and_sell_for_duration(self) -> None:
        response = self._post({"services": [{"id": self.service.pk, "duration": "01:00:00"}]})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["workshop_cost_missing"])
        self.assertEqual(payload["missing_ids"], [])
        self.assertEqual(len(payload["services"]), 1)
        row = payload["services"][0]
        self.assertEqual(row["id"], self.service.pk)
        self.assertIn("80", row["cost"])
        self.assertIn("160", row["sell"])

    def test_workshop_cost_missing_returns_warning_flag(self) -> None:
        self.workshop_cost.delete()
        response = self._post({"services": [{"id": self.service.pk, "duration": "00:30:00"}]})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["workshop_cost_missing"])
        self.assertEqual(payload["services"], [])

    def test_missing_service_ids_are_skipped_without_400(self) -> None:
        missing_id = self.service.pk + 9999
        response = self._post(
            {
                "services": [
                    {"id": self.service.pk, "duration": "01:00:00"},
                    {"id": missing_id, "duration": "00:30:00"},
                ]
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["workshop_cost_missing"])
        self.assertEqual(payload["missing_ids"], [missing_id])
        self.assertEqual(len(payload["services"]), 1)
        self.assertEqual(payload["services"][0]["id"], self.service.pk)

    def test_invalid_duration_returns_400(self) -> None:
        response = self._post({"services": [{"id": self.service.pk, "duration": "99:99:99"}]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_service_row")

    def test_get_current_workshop_cost_uses_localdate(self) -> None:
        from apps.catalog.util import get_current_workshop_cost

        with patch("apps.catalog.util.timezone.localdate", return_value=timezone.localdate()):
            cost, missing = get_current_workshop_cost(self.workshop)
        self.assertFalse(missing)
        self.assertEqual(cost, self.workshop_cost)

    def test_non_director_with_change_kit_can_bulk_price(self) -> None:
        staff_user = User.objects.create_user(username="kit-editor", password="secret", cpf="52998224725")
        staff_user.account = self.account
        staff_user.save(update_fields=["account"])

        role = WorkshopRole.objects.create(account=self.account, name="Estoquista")
        kit_ct = ContentType.objects.get_for_model(Kit)
        change_kit = Permission.objects.get(content_type=kit_ct, codename="change_kit")
        role.permissions.add(change_kit)
        WorkshopMember.objects.create(user=staff_user, workshop=self.workshop, role=role, is_active=True)

        self.client.force_login(staff_user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        response = self._post({"services": [{"id": self.service.pk, "duration": "00:30:00"}]})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["workshop_cost_missing"])
        self.assertEqual(len(payload["services"]), 1)
