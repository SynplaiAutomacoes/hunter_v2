from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import Account
from apps.catalog.models.products import Product
from apps.customer.models import Customer
from apps.finance.management.commands.seed_fiscal_demo import DEMO_MARKER, DEMO_SERIES
from apps.finance.models.finance import FiscalDocument, FiscalDocumentEvent, FiscalDocumentStatus, FiscalEmissionAttempt, NfeItem, NfeItemStatus, NfeRequest, NfeRequestManualItem, NfeRequestStatus, WebmaniaWebhookEvent
from apps.finance.services.nfe_complementary import is_local_nfe_eligible_for_complementary
from apps.finance.services.nfe_events import is_nfe_item_eligible_for_cce
from apps.finance.services.nfe_returns import is_local_nfe_eligible_for_return
from apps.stock.models import StockProduct
from apps.workshops.models.workshops import Workshop


@override_settings(DEBUG=True)
class SeedFiscalDemoCommandTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta massa fiscal")
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina massa fiscal",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua de Teste, 1",
        )

    def test_command_creates_idempotent_demo_dataset_without_remote_effects(self) -> None:
        first_output = StringIO()
        call_command("seed_fiscal_demo", workshop_id=self.workshop.pk, stdout=first_output)

        requests = NfeRequest.objects.filter(workshop=self.workshop, reserved_series=DEMO_SERIES, additional_information__contains=DEMO_MARKER)
        request_ids = list(requests.order_by("reserved_number").values_list("pk", flat=True))

        self.assertEqual(Customer.objects.filter(workshop=self.workshop, cpf_or_cnpj__in=["52998224725", "11222333000181"]).count(), 2)
        self.assertEqual(Product.objects.filter(workshop=self.workshop, code__startswith="FISCAL-DEMO-").count(), 4)
        self.assertEqual(StockProduct.objects.filter(workshop=self.workshop, product__code__startswith="FISCAL-DEMO-").count(), 4)
        self.assertEqual(requests.count(), 5)
        self.assertEqual(NfeRequestManualItem.objects.filter(request__in=requests).count(), 9)
        self.assertEqual(NfeItem.objects.filter(request__in=requests).count(), 5)
        self.assertEqual(FiscalDocument.objects.filter(legacy_nfe_item__request__in=requests).count(), 5)
        self.assertEqual(FiscalDocumentEvent.objects.filter(document__legacy_nfe_item__request__in=requests).count(), 1)
        self.assertEqual(FiscalEmissionAttempt.objects.count(), 0)
        self.assertEqual(WebmaniaWebhookEvent.objects.count(), 0)
        self.assertIn("A reexecucao nao duplica registros", first_output.getvalue())

        call_command("seed_fiscal_demo", workshop_id=self.workshop.pk, stdout=StringIO())

        self.assertEqual(list(requests.order_by("reserved_number").values_list("pk", flat=True)), request_ids)
        self.assertEqual(requests.count(), 5)
        self.assertEqual(NfeRequestManualItem.objects.filter(request__in=requests).count(), 9)
        self.assertEqual(NfeItem.objects.filter(request__in=requests).count(), 5)
        self.assertEqual(FiscalDocument.objects.filter(legacy_nfe_item__request__in=requests).count(), 5)
        self.assertEqual(FiscalDocumentEvent.objects.filter(document__legacy_nfe_item__request__in=requests).count(), 1)

    def test_approved_notes_are_eligible_and_canceled_note_is_not(self) -> None:
        call_command("seed_fiscal_demo", workshop_id=self.workshop.pk, stdout=StringIO())

        approved_items = NfeItem.objects.filter(request__workshop=self.workshop, request__reserved_series=DEMO_SERIES, status=NfeItemStatus.aprovado)
        canceled_item = NfeItem.objects.get(request__workshop=self.workshop, request__reserved_series=DEMO_SERIES, status=NfeItemStatus.cancelado)

        self.assertEqual(approved_items.count(), 4)
        for item in approved_items:
            self.assertTrue(is_nfe_item_eligible_for_cce(item))
            self.assertTrue(is_local_nfe_eligible_for_return(item))
            self.assertTrue(is_local_nfe_eligible_for_complementary(item))
            self.assertEqual(len(item.access_key), 44)
            self.assertTrue(item.xml_url.startswith("https://demo.invalid/"))
            self.assertTrue(item.raw_payload["demo_data"])

        self.assertFalse(is_nfe_item_eligible_for_cce(canceled_item))
        self.assertFalse(is_local_nfe_eligible_for_return(canceled_item))
        self.assertFalse(is_local_nfe_eligible_for_complementary(canceled_item))
        self.assertEqual(canceled_item.request.status, NfeRequestStatus.CANCELED)
        self.assertEqual(canceled_item.fiscal_document.status, FiscalDocumentStatus.CANCELED)

    @override_settings(DEBUG=False)
    def test_command_refuses_to_run_outside_debug(self) -> None:
        with self.assertRaisesMessage(CommandError, "DEBUG=True"):
            call_command("seed_fiscal_demo", workshop_id=self.workshop.pk, stdout=StringIO())

    def test_command_requires_an_existing_workshop(self) -> None:
        with self.assertRaisesMessage(CommandError, "Oficina nao encontrada"):
            call_command("seed_fiscal_demo", workshop_id=999999, stdout=StringIO())
