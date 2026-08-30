from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import Account
from apps.terms.defaults import default_vehicle_receipt_content
from apps.terms.models import TermTemplateType, WorkshopTermTemplate
from apps.workshops.models.workshops import Workshop


class WorkshopTermTemplateModelTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta Termos")
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Termos",
            cnpj="11.222.333/0001-44",
            phone="+5511999999999",
            address="Rua Termos, 10",
        )

    def test_multiple_templates_per_workshop_and_type(self) -> None:
        first = WorkshopTermTemplate.objects.create(
            workshop=self.workshop,
            template_type=TermTemplateType.VEHICLE_RECEIPT,
            name="Recebimento A",
            document_title="TERMO A",
            is_default=True,
            content=default_vehicle_receipt_content(),
        )
        second = WorkshopTermTemplate.objects.create(
            workshop=self.workshop,
            template_type=TermTemplateType.VEHICLE_RECEIPT,
            name="Recebimento B",
            document_title="TERMO B",
            is_default=True,
            content=default_vehicle_receipt_content(),
        )
        self.assertEqual(WorkshopTermTemplate.objects.filter(workshop=self.workshop, template_type=TermTemplateType.VEHICLE_RECEIPT).count(), 2)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
