from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import TestCase
from django.utils import timezone

from apps.budget.models import Budget
from apps.customer.models import Customer, Vehicle
from apps.workorder.models import WorkOrder, WorkOrderWarrantyPlan
from apps.workorder.pdf_context import build_workorder_pdf_context
from apps.workshops.models.workshops import Workshop


def _create_workorder(*, suffix: int) -> WorkOrder:
    workshop = Workshop.objects.create(
        name=f"Oficina PDF {suffix}",
        cnpj=f"11.222.333/0002-{suffix:02d}",
        phone="+5511999999999",
        address="Rua PDF, 100",
    )
    customer = Customer.objects.create(
        workshop=workshop,
        name=f"Cliente PDF {suffix}",
        cpf_or_cnpj=f"1234567891{suffix:02d}",
        email=f"pdf{suffix}@example.com",
        is_active=True,
    )
    vehicle = Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=f"PDF{suffix:04d}",
        brand="Fiat",
        model="Uno",
        year_fabrication="2020",
        year_model="2020",
    )
    budget = Budget.objects.create(
        workshop=workshop,
        customer=customer,
        vehicle=vehicle,
        entry_date=timezone.localdate(),
        slider=0,
        service_expected_completion_at=timezone.make_aware(datetime(2026, 8, 10, 9, 0)),
        customer_agreed_departure_at=timezone.make_aware(datetime(2026, 8, 12, 18, 0)),
    )
    return WorkOrder.objects.create(workshop=workshop, budget=budget)


class WorkOrderPdfContextTests(TestCase):
    def test_os_pdf_uses_now_as_delivery_when_not_finalized(self) -> None:
        workorder = _create_workorder(suffix=1)
        workorder.warranty_plan = WorkOrderWarrantyPlan.DAYS_90
        workorder.save(update_fields=["warranty_plan"])
        now = timezone.make_aware(datetime(2026, 8, 23, 14, 47))

        with (
            patch("apps.workorder.pdf_context.timezone.now", return_value=now),
            patch("apps.workorder.pdf_context.timezone.localdate", return_value=now.date()),
        ):
            context = build_workorder_pdf_context(workorder=workorder)
        html = render_to_string("workorder/partials/pdf/visualizarPDF.html", context)

        self.assertIsNone(workorder.delivered_at)
        self.assertEqual(context["pdf_delivered_at"], now)
        self.assertIsNone(context["expected_delivery_at"])
        self.assertNotIn("Data prevista de entrega", html)
        self.assertIn("Entrega do veículo feita no dia", html)
        self.assertIn("23/08/2026", html)
        self.assertIn("14:47", html)
        self.assertIn("Garantia: 90 dias", html)
        self.assertIn("21/11/2026", html)
        self.assertIn("Em garantia", html)

    def test_os_pdf_keeps_persisted_delivery_when_finalized(self) -> None:
        workorder = _create_workorder(suffix=2)
        workorder.delivered_at = timezone.make_aware(datetime(2026, 8, 6, 16, 0))
        workorder.warranty_plan = WorkOrderWarrantyPlan.DAYS_90
        workorder.save(update_fields=["delivered_at", "warranty_plan"])

        context = build_workorder_pdf_context(workorder=workorder)
        html = render_to_string("workorder/partials/pdf/visualizarPDF.html", context)

        self.assertEqual(context["pdf_delivered_at"], workorder.delivered_at)
        self.assertIsNone(context["expected_delivery_at"])
        self.assertNotIn("Data prevista de entrega", html)
        self.assertIn("Entrega do veículo feita no dia", html)
        self.assertIn("06/08/2026", html)
        self.assertIn("16:00", html)
        self.assertIn("Garantia: 90 dias", html)
        self.assertIn("válida até", html)
        self.assertIn("04/11/2026", html)
        self.assertIn("Em garantia", html)

    def test_os_pdf_keeps_ordem_de_servico_title(self) -> None:
        workorder = _create_workorder(suffix=3)
        context = build_workorder_pdf_context(workorder=workorder)
        html = render_to_string("workorder/partials/pdf/visualizarPDF.html", context)

        self.assertEqual(context["document_title"], "ORDEM DE SERVIÇO")
        self.assertIn("ORDEM DE SERVIÇO", html)
        self.assertNotIn(">ORÇAMENTO<", html)
