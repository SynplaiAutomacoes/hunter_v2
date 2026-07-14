from __future__ import annotations

import json
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.budget.models import Budget, BudgetStatus
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workorder.views import UpdateWorkOrderKmFinalView
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class UpdateWorkOrderKmFinalViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = Workshop.objects.create(
            name="Oficina KM Final",
            cnpj="91.222.333/0001-99",
            phone="+5511999999999",
            address="Rua KM, 123",
            uf="SP",
        )
        self.user = User.objects.create_user(username="km-final", password="senha123", cpf="12345678901")
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 12),
            status=BudgetStatus.DRAFT,
            budget_type="courtesy",
            current_step=6,
            current_km=1000,
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.DRAFT,
            budget_type="courtesy",
        )

    def test_update_km_final_returns_refreshed_blocker_flags_when_km_was_only_blocker(self) -> None:
        self.assertTrue(self.workorder.has_signature_blockers)
        self.assertTrue(self.workorder.has_completion_blockers)
        self.assertIn("Km Final", self.workorder.signature_blockers_display)

        request = self.factory.post(
            f"/workorder/{self.workorder.pk}/update-km-final/",
            {"km_final": "1500"},
        )
        request.user = self.user
        SessionMiddleware(lambda req: HttpResponse()).process_request(request)
        request.session.save()

        view = UpdateWorkOrderKmFinalView()
        view.request = request
        view.workshop = self.workshop

        response = view.post(request, pk=self.workorder.pk)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["km_final"], 1500)
        self.assertFalse(payload["has_completion_blockers"])
        self.assertFalse(payload["has_signature_blockers"])
        self.assertEqual(payload["completion_blockers_display"], "")
        self.assertEqual(payload["signature_blockers_display"], "")

        self.workorder.refresh_from_db()
        self.assertEqual(self.workorder.km_final, 1500)
        self.assertFalse(self.workorder.has_signature_blockers)
        self.assertFalse(self.workorder.has_completion_blockers)
