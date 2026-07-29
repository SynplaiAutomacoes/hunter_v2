from __future__ import annotations

from django.test import TestCase

from apps.finance.models import FinancialGroup, PaymentMethod
from apps.quote.models.investigative_questions import InvestigativeQuestion
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.default_setup import (
    DEFAULT_FINANCIAL_GROUPS,
    DEFAULT_INVESTIGATIVE_QUESTIONS,
    DEFAULT_PAYMENT_METHODS,
    create_default_workshop_setup,
)


class CreateDefaultWorkshopSetupTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Default Setup",
            cnpj="68.333.444/0001-01",
            phone="+5511767676767",
            address="Rua Default, 100",
        )

    def test_seeds_payment_methods_financial_groups_and_investigative_questions(self) -> None:
        summary = create_default_workshop_setup(workshop=self.workshop)

        self.assertEqual(summary["payment_methods_created"], len(DEFAULT_PAYMENT_METHODS))
        self.assertEqual(summary["financial_groups_created"], len(DEFAULT_FINANCIAL_GROUPS))
        self.assertEqual(summary["investigative_questions_created"], len(DEFAULT_INVESTIGATIVE_QUESTIONS))

        self.assertTrue(PaymentMethod.objects.filter(workshop=self.workshop, description="Dinheiro a vista").exists())
        self.assertFalse(PaymentMethod.objects.filter(workshop=self.workshop, description="Teste").exists())
        self.assertFalse(PaymentMethod.objects.filter(workshop=self.workshop, description="BOLETO").exists())

        departamento = FinancialGroup.objects.get(workshop=self.workshop, name="Departamento Pessoal", parent__isnull=True)
        self.assertEqual(departamento.code, "5")

        salario = FinancialGroup.objects.get(workshop=self.workshop, name="Salarios Mensais")
        self.assertEqual(salario.code, "5.1.11")

        comissao = FinancialGroup.objects.get(workshop=self.workshop, name="Comissão")
        self.assertEqual(comissao.code, "5.1.5")

        vale = FinancialGroup.objects.get(workshop=self.workshop, name="Vale Transporte de Funcionários")
        self.assertEqual(vale.code, "5.1.13")

        question = InvestigativeQuestion.objects.get(workshop=self.workshop, text="Veículo possui seguro?")
        self.assertEqual(question.response_type, InvestigativeQuestion.ResponseType.BOOLEAN)
        self.assertEqual(question.order, 0)

    def test_running_twice_is_idempotent(self) -> None:
        first = create_default_workshop_setup(workshop=self.workshop)
        second = create_default_workshop_setup(workshop=self.workshop)

        self.assertGreater(first["payment_methods_created"], 0)
        self.assertEqual(second["payment_methods_created"], 0)
        self.assertEqual(second["financial_groups_created"], 0)
        self.assertEqual(second["investigative_questions_created"], 0)

        self.assertEqual(PaymentMethod.objects.filter(workshop=self.workshop).count(), len(DEFAULT_PAYMENT_METHODS))
        self.assertEqual(FinancialGroup.objects.filter(workshop=self.workshop).count(), len(DEFAULT_FINANCIAL_GROUPS))
        self.assertEqual(
            InvestigativeQuestion.objects.filter(workshop=self.workshop).count(),
            len(DEFAULT_INVESTIGATIVE_QUESTIONS),
        )

    def test_reuses_preexisting_despesas_folha_without_duplicating(self) -> None:
        despesas = FinancialGroup.objects.create(workshop=self.workshop, name="Despesas")
        FinancialGroup.objects.create(workshop=self.workshop, parent=despesas, name="Folha de Pagamento")

        summary = create_default_workshop_setup(workshop=self.workshop)

        self.assertEqual(summary["financial_groups_created"], len(DEFAULT_FINANCIAL_GROUPS) - 2)
        self.assertEqual(FinancialGroup.objects.filter(workshop=self.workshop, name="Despesas").count(), 1)
        self.assertEqual(FinancialGroup.objects.filter(workshop=self.workshop, name="Folha de Pagamento").count(), 1)
