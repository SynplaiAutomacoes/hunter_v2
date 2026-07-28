from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase, TestCase
from djmoney.money import Money

from apps.collaborators.models import WorkshopCollaborator
from apps.collaborators.test_commissions import create_financial_group_path
from apps.finance.forms.financial_movement import MovementStep3Form, ReportMovementEditForm
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.financial_movement import (
    BUDGET_PLAN_REQUIRED_FOR_RECONCILIATION,
    apply_payment_reconciliation_rules,
)
from apps.finance.views.payroll import PayrollPaymentForm
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Reconciliacao {suffix}",
        cnpj=f"71.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Reconciliacao, 123",
    )


class ApplyPaymentReconciliationRulesTests(SimpleTestCase):
    def test_unpaid_forces_awaiting_reconciliation(self) -> None:
        cleaned_data: dict[str, object] = {"is_paid": False, "is_reconciled": True, "budget_plan": object()}

        errors = apply_payment_reconciliation_rules(cleaned_data)

        self.assertEqual(errors, [])
        self.assertFalse(cleaned_data["is_reconciled"])

    def test_reconciled_without_budget_plan_returns_error(self) -> None:
        cleaned_data: dict[str, object] = {"is_paid": True, "is_reconciled": True, "budget_plan": None}

        errors = apply_payment_reconciliation_rules(cleaned_data)

        self.assertEqual(errors, [("budget_plan", BUDGET_PLAN_REQUIRED_FOR_RECONCILIATION)])

    def test_paid_reconciled_with_budget_plan_is_valid(self) -> None:
        cleaned_data: dict[str, object] = {"is_paid": True, "is_reconciled": True, "budget_plan": object()}

        errors = apply_payment_reconciliation_rules(cleaned_data)

        self.assertEqual(errors, [])
        self.assertTrue(cleaned_data["is_reconciled"])


class PaymentReconciliationFormTests(TestCase):
    def _create_payment_method(self, *, workshop: Workshop) -> PaymentMethod:
        return PaymentMethod.objects.create(
            workshop=workshop,
            description="Pix",
            payment_type=PaymentMethod.PaymentType.BOTH,
            is_active=True,
        )

    def _create_supplier(self, *, workshop: Workshop, suffix: int) -> Supplier:
        return Supplier.objects.create(
            workshop=workshop,
            name=f"Fornecedor {suffix}",
            cnpj=f"12.345.678/0001-{suffix:02d}",
        )

    def test_report_edit_form_unpaid_resets_reconciliation(self) -> None:
        workshop = create_workshop(suffix=1)
        supplier = self._create_supplier(workshop=workshop, suffix=1)
        payment_method = self._create_payment_method(workshop=workshop)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Despesa teste",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
            is_paid=True,
            is_reconciled=True,
        )

        form = ReportMovementEditForm(
            data={
                "supplier": str(supplier.pk),
                "description": "Despesa teste",
                "due_date": "2026-08-05",
                "direction": FinancialMovement.MovementDirection.DEBIT,
                "amount_0": "100.00",
                "amount_1": "BRL",
                "payment_method": str(payment_method.pk),
                "is_paid": "False",
                "is_reconciled": "True",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["is_reconciled"])

    def test_report_edit_form_reconciled_requires_budget_plan(self) -> None:
        workshop = create_workshop(suffix=2)
        supplier = self._create_supplier(workshop=workshop, suffix=2)
        payment_method = self._create_payment_method(workshop=workshop)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Despesa teste",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
            is_paid=True,
            is_reconciled=False,
        )

        form = ReportMovementEditForm(
            data={
                "supplier": str(supplier.pk),
                "description": "Despesa teste",
                "due_date": "2026-08-05",
                "direction": FinancialMovement.MovementDirection.DEBIT,
                "amount_0": "100.00",
                "amount_1": "BRL",
                "payment_method": str(payment_method.pk),
                "is_paid": "True",
                "is_reconciled": "True",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("budget_plan", form.errors)
        self.assertEqual(form.errors["budget_plan"][0], BUDGET_PLAN_REQUIRED_FOR_RECONCILIATION)

    def test_report_edit_form_paid_reconciled_with_budget_plan_is_valid(self) -> None:
        workshop = create_workshop(suffix=3)
        supplier = self._create_supplier(workshop=workshop, suffix=3)
        payment_method = self._create_payment_method(workshop=workshop)
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[1], names=["Plano"])
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Despesa teste",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
            budget_plan=budget_plan,
            is_paid=True,
            is_reconciled=False,
        )

        form = ReportMovementEditForm(
            data={
                "supplier": str(supplier.pk),
                "description": "Despesa teste",
                "due_date": "2026-08-05",
                "direction": FinancialMovement.MovementDirection.DEBIT,
                "amount_0": "100.00",
                "amount_1": "BRL",
                "payment_method": str(payment_method.pk),
                "budget_plan": str(budget_plan.pk),
                "is_paid": "True",
                "is_reconciled": "True",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["is_reconciled"])
        self.assertEqual(form.cleaned_data["budget_plan"], budget_plan)

    def test_step3_and_payroll_forms_apply_same_rules(self) -> None:
        workshop = create_workshop(suffix=4)
        collaborator = WorkshopCollaborator.objects.create(
            workshop=workshop,
            name="Colaborador Reconciliacao",
            cpf="12345678904",
            birth_date=date(1990, 1, 1),
            salary=Money(2000, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )
        payment_method = self._create_payment_method(workshop=workshop)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Pagamento folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
            is_paid=True,
            is_reconciled=True,
        )

        step3_form = MovementStep3Form(
            data={
                "due_date": "2026-08-05",
                "amount_0": "2000.00",
                "amount_1": "BRL",
                "payment_method": str(payment_method.pk),
                "is_paid": "False",
                "is_reconciled": "True",
            },
            instance=movement,
            workshop=workshop,
        )
        payroll_form = PayrollPaymentForm(
            data={
                "due_date": "2026-08-05",
                "amount_0": "2000.00",
                "amount_1": "BRL",
                "is_paid": "False",
                "is_reconciled": "True",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertTrue(step3_form.is_valid(), step3_form.errors)
        self.assertFalse(step3_form.cleaned_data["is_reconciled"])
        self.assertTrue(payroll_form.is_valid(), payroll_form.errors)
        self.assertFalse(payroll_form.cleaned_data["is_reconciled"])
