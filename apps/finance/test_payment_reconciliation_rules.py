from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase, TestCase
from djmoney.money import Money

from apps.collaborators.models import WorkshopCollaborator
from apps.collaborators.test_commissions import create_financial_group_path
from apps.finance.forms.financial_movement import MovementStep3Form, ReportMovementEditForm
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.financial_movement import (
    BANK_ACCOUNT_REQUIRED_FOR_RECONCILIATION,
    BUDGET_PLAN_REQUIRED,
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
        cleaned_data: dict[str, object] = {"is_paid": True, "is_reconciled": True, "budget_plan": None, "bank_account": object()}

        errors = apply_payment_reconciliation_rules(cleaned_data)

        self.assertEqual(errors, [("budget_plan", BUDGET_PLAN_REQUIRED_FOR_RECONCILIATION)])

    def test_reconciled_without_bank_account_returns_error(self) -> None:
        cleaned_data: dict[str, object] = {"is_paid": True, "is_reconciled": True, "budget_plan": object(), "bank_account": None}

        errors = apply_payment_reconciliation_rules(cleaned_data)

        self.assertEqual(errors, [("bank_account", BANK_ACCOUNT_REQUIRED_FOR_RECONCILIATION)])

    def test_paid_reconciled_with_budget_plan_is_valid(self) -> None:
        cleaned_data: dict[str, object] = {"is_paid": True, "is_reconciled": True, "budget_plan": object(), "bank_account": object()}

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

    def _create_bank_account(self, *, workshop: Workshop, suffix: int, is_active: bool = True) -> BankAccount:
        return BankAccount.objects.create(
            workshop=workshop,
            bank_code="341",
            bank_name="Itaú",
            account_type=BankAccount.AccountType.CORRENTE,
            agency="0001",
            account_number=f"12345-{suffix}",
            is_active=is_active,
        )

    def _create_supplier(self, *, workshop: Workshop, suffix: int) -> Supplier:
        return Supplier.objects.create(
            workshop=workshop,
            name=f"Fornecedor {suffix}",
            cnpj=f"12.345.678/0001-{suffix:02d}",
        )

    @staticmethod
    def _financial_amount_fields(*, amount: str = "100.00", entry_date: str = "2026-08-05") -> dict[str, str]:
        return {
            "entry_date": entry_date,
            "gross_amount_0": amount,
            "gross_amount_1": "BRL",
            "discount_mode": FinancialMovement.DiscountMode.NONE,
            "discount_value_0": "0.00",
            "discount_value_1": "BRL",
            "amount_0": amount,
            "amount_1": "BRL",
        }

    def test_report_edit_form_unpaid_resets_reconciliation(self) -> None:
        workshop = create_workshop(suffix=1)
        supplier = self._create_supplier(workshop=workshop, suffix=1)
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
            is_reconciled=True,
        )

        form = ReportMovementEditForm(
            data={
                "supplier": str(supplier.pk),
                "description": "Despesa teste",
                "due_date": "2026-08-05",
                "direction": FinancialMovement.MovementDirection.DEBIT,
                **self._financial_amount_fields(),
                "payment_method": str(payment_method.pk),
                "budget_plan": str(budget_plan.pk),
                "is_paid": "False",
                "is_reconciled": "True",
                "is_partial_payment": "False",
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
        bank_account = self._create_bank_account(workshop=workshop, suffix=2)
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
                "bank_account": str(bank_account.pk),
                "is_paid": "True",
                "is_reconciled": "True",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("budget_plan", form.errors)
        self.assertEqual(form.errors["budget_plan"][0], BUDGET_PLAN_REQUIRED)

    def test_report_edit_form_requires_budget_plan_when_unpaid(self) -> None:
        workshop = create_workshop(suffix=21)
        supplier = self._create_supplier(workshop=workshop, suffix=21)
        payment_method = self._create_payment_method(workshop=workshop)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Despesa teste",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
            is_paid=False,
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
                "is_paid": "False",
                "is_reconciled": "False",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("budget_plan", form.errors)
        self.assertEqual(form.errors["budget_plan"][0], BUDGET_PLAN_REQUIRED)

    def test_report_edit_form_reconciled_requires_bank_account(self) -> None:
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

        self.assertFalse(form.is_valid())
        self.assertIn("bank_account", form.errors)
        self.assertEqual(form.errors["bank_account"][0], BANK_ACCOUNT_REQUIRED_FOR_RECONCILIATION)

    def test_report_edit_form_paid_reconciled_with_budget_plan_is_valid(self) -> None:
        workshop = create_workshop(suffix=4)
        supplier = self._create_supplier(workshop=workshop, suffix=4)
        payment_method = self._create_payment_method(workshop=workshop)
        bank_account = self._create_bank_account(workshop=workshop, suffix=4)
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
                **self._financial_amount_fields(),
                "payment_method": str(payment_method.pk),
                "budget_plan": str(budget_plan.pk),
                "bank_account": str(bank_account.pk),
                "is_paid": "True",
                "is_reconciled": "True",
                "is_partial_payment": "False",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["is_reconciled"])
        self.assertEqual(form.cleaned_data["budget_plan"], budget_plan)
        self.assertEqual(form.cleaned_data["bank_account"], bank_account)

    def test_report_edit_form_partial_payment_creates_pending_balance(self) -> None:
        workshop = create_workshop(suffix=41)
        supplier = self._create_supplier(workshop=workshop, suffix=41)
        payment_method = self._create_payment_method(workshop=workshop)
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[1], names=["Plano"])
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Peças",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
            budget_plan=budget_plan,
        )

        form = ReportMovementEditForm(
            data={
                "supplier": str(supplier.pk),
                "description": "Peças",
                "entry_date": "2026-08-05",
                "due_date": "2026-08-05",
                "direction": FinancialMovement.MovementDirection.DEBIT,
                "gross_amount_0": "100.00",
                "gross_amount_1": "BRL",
                "discount_mode": FinancialMovement.DiscountMode.NONE,
                "discount_value_0": "0.00",
                "discount_value_1": "BRL",
                "amount_0": "100.00",
                "amount_1": "BRL",
                "budget_plan": str(budget_plan.pk),
                "payment_method": str(payment_method.pk),
                "is_paid": "False",
                "is_reconciled": "False",
                "is_partial_payment": "True",
                "partial_payment_amount_0": "40.00",
                "partial_payment_amount_1": "BRL",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        movement.refresh_from_db()
        balance = FinancialMovement.objects.get(partial_payment_of=movement)
        self.assertEqual(movement.amount, Money(40, "BRL"))
        self.assertTrue(movement.is_paid)
        self.assertEqual(balance.amount, Money(60, "BRL"))
        self.assertFalse(balance.is_paid)
        self.assertFalse(balance.is_reconciled)
        self.assertEqual(balance.supplier, supplier)

    def test_report_edit_form_keeps_original_paid_status_after_invalid_partial_payment(self) -> None:
        workshop = create_workshop(suffix=43)
        supplier = self._create_supplier(workshop=workshop, suffix=43)
        payment_method = self._create_payment_method(workshop=workshop)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Peças",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
            is_paid=False,
        )

        form = ReportMovementEditForm(
            data={
                "supplier": str(supplier.pk),
                "description": "",
                "due_date": "2026-08-05",
                "direction": FinancialMovement.MovementDirection.DEBIT,
                "amount_0": "100.00",
                "amount_1": "BRL",
                "payment_method": str(payment_method.pk),
                "is_paid": "False",
                "is_reconciled": "False",
                "is_partial_payment": "True",
                "partial_payment_amount_0": "40.00",
                "partial_payment_amount_1": "BRL",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)
        self.assertTrue(form.instance.is_paid)
        self.assertFalse(form.was_initially_paid)
        self.assertEqual(form.data["is_partial_payment"], "True")
        self.assertEqual(form.data["partial_payment_amount_0"], "40.00")

    def test_report_edit_form_rejects_partial_payment_equal_to_total(self) -> None:
        workshop = create_workshop(suffix=42)
        supplier = self._create_supplier(workshop=workshop, suffix=42)
        payment_method = self._create_payment_method(workshop=workshop)
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[1], names=["Plano"])
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Peças",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
        )
        form = ReportMovementEditForm(
            data={
                "supplier": str(supplier.pk), "description": "Peças", "entry_date": "2026-08-05", "due_date": "2026-08-05",
                "direction": FinancialMovement.MovementDirection.DEBIT,
                "gross_amount_0": "100.00",
                "gross_amount_1": "BRL",
                "discount_mode": FinancialMovement.DiscountMode.NONE,
                "discount_value_0": "0.00",
                "discount_value_1": "BRL",
                "amount_0": "100.00",
                "amount_1": "BRL",
                "budget_plan": str(budget_plan.pk),
                "payment_method": str(payment_method.pk),
                "is_paid": "True",
                "is_reconciled": "False",
                "is_partial_payment": "True", "partial_payment_amount_0": "100.00", "partial_payment_amount_1": "BRL",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("partial_payment_amount", form.errors)

    def test_step3_and_payroll_forms_apply_same_rules(self) -> None:
        workshop = create_workshop(suffix=5)
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
        budget_plan = create_financial_group_path(workshop=workshop, code_segments=[1], names=["Plano"])
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Pagamento folha",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
            budget_plan=budget_plan,
            is_paid=True,
            is_reconciled=True,
        )

        step3_form = MovementStep3Form(
            data={
                "due_date": "2026-08-05",
                **self._financial_amount_fields(amount="2000.00"),
                "payment_method": str(payment_method.pk),
                "budget_plan": str(budget_plan.pk),
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
                "budget_plan": str(budget_plan.pk),
                "is_paid": "False",
                "is_reconciled": "True",
                "is_partial_payment": "False",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertTrue(step3_form.is_valid(), step3_form.errors)
        self.assertFalse(step3_form.cleaned_data["is_reconciled"])
        self.assertTrue(payroll_form.is_valid(), payroll_form.errors)
        self.assertFalse(payroll_form.cleaned_data["is_reconciled"])

    def test_step3_form_requires_budget_plan(self) -> None:
        workshop = create_workshop(suffix=22)
        payment_method = self._create_payment_method(workshop=workshop)
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Despesa teste",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
        )

        form = MovementStep3Form(
            data={
                "due_date": "2026-08-05",
                "amount_0": "100.00",
                "amount_1": "BRL",
                "payment_method": str(payment_method.pk),
                "is_paid": "False",
                "is_reconciled": "False",
            },
            instance=movement,
            workshop=workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("budget_plan", form.errors)
        self.assertEqual(form.errors["budget_plan"][0], BUDGET_PLAN_REQUIRED)

    def test_inactive_bank_accounts_excluded_from_movement_forms(self) -> None:
        workshop = create_workshop(suffix=6)
        active_account = self._create_bank_account(workshop=workshop, suffix=10, is_active=True)
        inactive_account = self._create_bank_account(workshop=workshop, suffix=11, is_active=False)
        payment_method = self._create_payment_method(workshop=workshop)

        movement = FinancialMovement.objects.create(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Despesa teste",
            amount=Money(100, "BRL"),
            due_date=date(2026, 8, 5),
            payment_method=payment_method,
        )

        edit_form = ReportMovementEditForm(instance=movement, workshop=workshop)
        edit_bank_account_pks = [pk for pk, _ in edit_form.fields["bank_account"].widget.choices]
        self.assertIn(active_account.pk, edit_bank_account_pks)
        self.assertNotIn(inactive_account.pk, edit_bank_account_pks)
        self.assertEqual(edit_form.fields["budget_plan"].widget.choices[0], ("", "---------"))
        self.assertTrue(edit_form.fields["budget_plan"].required)

        step3_form = MovementStep3Form(instance=movement, workshop=workshop)
        step3_bank_account_pks = [pk for pk, _ in step3_form.fields["bank_account"].widget.choices]
        self.assertIn(active_account.pk, step3_bank_account_pks)
        self.assertNotIn(inactive_account.pk, step3_bank_account_pks)
        self.assertEqual(step3_form.fields["budget_plan"].widget.choices[0], ("", "---------"))
        self.assertTrue(step3_form.fields["budget_plan"].required)
