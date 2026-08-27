from django.test import TestCase
from django.test import RequestFactory
from unittest.mock import patch

from apps.customer.forms import CustomerForm, QuickCustomerForm
from apps.customer.models import Customer
from apps.customer.views import api_check_customer_document
from apps.workshops.models.workshops import Workshop


class CustomerDocumentNormalizationTests(TestCase):
    document = "04.252.011/0001-10"

    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Documento",
            cnpj="41.222.333/0001-01",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )

    def _data(self) -> dict[str, str]:
        return {
            "customer_type": "PJ",
            "cpf_or_cnpj": self.document,
            "name": "Empresa Documento Ltda",
            "email": "documento@example.com",
            "cep": "01001-000",
            "logradouro": "Rua Teste",
            "numero": "1",
            "bairro": "Centro",
            "cidade": "Sao Paulo",
            "estado": "SP",
        }

    def _create_legacy_masked_customer(self) -> Customer:
        customer = Customer.objects.create(workshop=self.workshop, **self._data())
        Customer.objects.filter(pk=customer.pk).update(cpf_or_cnpj=self.document)
        customer.refresh_from_db()
        return customer

    def test_model_saves_document_with_digits_only(self) -> None:
        customer = Customer.objects.create(workshop=self.workshop, **self._data())

        self.assertEqual(customer.cpf_or_cnpj, "04252011000110")

    def test_customer_form_blocks_legacy_masked_document(self) -> None:
        self._create_legacy_masked_customer()

        form = CustomerForm(data=self._data(), workshop=self.workshop)

        self.assertFalse(form.is_valid())
        self.assertIn("Já existe um cliente cadastrado", str(form.errors["cpf_or_cnpj"]))

    def test_quick_customer_form_blocks_legacy_masked_document(self) -> None:
        self._create_legacy_masked_customer()

        form = QuickCustomerForm(data=self._data(), workshop=self.workshop)

        self.assertFalse(form.is_valid())
        self.assertIn("Já existe um cliente cadastrado", str(form.errors["cpf_or_cnpj"]))

    @patch("apps.customer.views.get_active_workshop_or_404")
    def test_document_check_endpoint_finds_legacy_masked_document(self, active_workshop) -> None:
        self._create_legacy_masked_customer()
        active_workshop.return_value = self.workshop

        response = api_check_customer_document(RequestFactory().get("/customer/check-document/", {"document": "04252011000110"}))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"exists": True})
