from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.customer.forms import QuickCustomerForm
from apps.customer.models import Customer
from apps.workshops.models.workshops import Workshop


class QuickCustomerFormTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Quick Customer",
            cnpj="41.222.333/0001-01",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )

    def test_form_includes_birth_date_and_sex_fields(self) -> None:
        form = QuickCustomerForm(workshop=self.workshop)

        self.assertIn("birth_date", form.fields)
        self.assertIn("sex", form.fields)

    def test_pf_form_saves_sex_and_birth_date(self) -> None:
        form = QuickCustomerForm(
            data={
                "customer_type": "PF",
                "cpf_or_cnpj": "52998224725",
                "name": "Maria Silva",
                "phone": "+5511988887777",
                "email": "maria@example.com",
                "birth_date": "1990-05-15",
                "sex": "F",
                "cep": "01001-000",
                "logradouro": "Praca da Se",
                "numero": "1",
                "bairro": "Se",
                "cidade": "Sao Paulo",
                "estado": "SP",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["birth_date"], date(1990, 5, 15))
        self.assertEqual(form.cleaned_data["sex"], "F")

        form.instance.workshop = self.workshop
        customer = form.save()

        self.assertEqual(customer.birth_date, date(1990, 5, 15))
        self.assertEqual(customer.sex, "F")
        self.assertEqual(Customer.objects.filter(pk=customer.pk).count(), 1)
