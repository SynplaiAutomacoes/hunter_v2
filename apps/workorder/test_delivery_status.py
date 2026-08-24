from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.budget.models import Budget
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.iam.models import WorkshopRole
from apps.workorder.models import WorkOrder, WorkOrderStatus, WorkOrderWarrantyPlan
from apps.workshops.models.workshops import Workshop


User = get_user_model()


def _create_workshop(*, suffix: int) -> Workshop:
    account = Account.objects.create(name=f"Conta Entrega {suffix}")
    return Workshop.objects.create(
        account=account,
        name=f"Oficina Entrega {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Entrega, 100",
    )


def _create_workorder(*, workshop: Workshop, suffix: int, status: str = WorkOrderStatus.DRAFT) -> WorkOrder:
    customer = Customer.objects.create(
        workshop=workshop,
        name=f"Cliente Entrega {suffix}",
        cpf_or_cnpj=f"1234567890{suffix:02d}",
        email=f"entrega{suffix}@example.com",
        is_active=True,
    )
    vehicle = Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=f"ENT{suffix:04d}",
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
    )
    return WorkOrder.objects.create(workshop=workshop, budget=budget, status=status)


class WorkOrderDeliveryStatusGateTests(TestCase):
    def test_open_workorders_can_change_delivery_status(self) -> None:
        workshop = _create_workshop(suffix=1)
        workorder = _create_workorder(workshop=workshop, suffix=1)

        self.assertTrue(workorder.can_change_delivery_status)

        workorder.status = WorkOrderStatus.WAITING_COLLABORATOR
        workorder.save(update_fields=["status"])
        self.assertTrue(workorder.can_change_delivery_status)

        workorder.status = WorkOrderStatus.WAITING_DELIVERY
        workorder.save(update_fields=["status"])
        self.assertTrue(workorder.can_change_delivery_status)

        workorder.status = WorkOrderStatus.APPROVED
        workorder.save(update_fields=["status"])
        self.assertFalse(workorder.can_change_delivery_status)


class UpdateWorkOrderStatusViewGateTests(TestCase):
    def setUp(self) -> None:
        self.workshop = _create_workshop(suffix=10)
        self.user = User.objects.create_user(username="entrega-os-user", password="secret", cpf="52998224725")
        self.user.account = self.workshop.account
        self.user.save(update_fields=["account"])
        role = WorkshopRole.objects.create(account=self.workshop.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.workorder = _create_workorder(workshop=self.workshop, suffix=10)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_draft_can_be_cancelled_without_delivery_step(self) -> None:
        url = reverse("workorder:update_status", kwargs={"pk": self.workorder.pk, "status": "cancel"})
        response = self.client.post(url, data={"status_reason": "Cancelar O.S. aberta"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get("HX-Refresh"), "true")
        self.assertNotIn("Conclua a etapa de entrega", response.get("HX-Trigger", ""))
        self.workorder.refresh_from_db()
        self.assertEqual(self.workorder.status, WorkOrderStatus.CANCELLED)
        self.assertTrue(self.workorder.cancellation_reason)

    def test_draft_can_be_delivered_without_delivery_step(self) -> None:
        url = reverse("workorder:update_status", kwargs={"pk": self.workorder.pk, "status": "approve"})
        response = self.client.post(
            url,
            data={
                "km_final": "12000",
                "warranty_plan": WorkOrderWarrantyPlan.DAYS_90,
                "unsigned_delivery_reason": "Cliente retirou sem assinar.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Conclua a etapa de entrega", response.get("HX-Trigger", ""))
        self.assertEqual(response.get("HX-Refresh"), "true")
        self.workorder.refresh_from_db()
        self.assertEqual(self.workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(self.workorder.km_final, 12000)
        self.assertEqual(self.workorder.warranty_plan, WorkOrderWarrantyPlan.DAYS_90)
