from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import Account
from apps.budget.forms.steps.step2_form import BudgetStep2Form
from apps.budget.models import Budget, SignatureStatus
from apps.terms.models import BudgetTermSigning, TermTemplateType, WorkshopTermTemplate
from apps.terms.selectors import update_budget_term_template
from apps.workshops.models.workshops import Workshop


class BudgetStep2TermTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta Step2 Termo")
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Step2",
            cnpj="22.333.444/0001-55",
            phone="+5511888888888",
            address="Rua Step2, 20",
        )
        self.term_a = WorkshopTermTemplate.objects.create(
            workshop=self.workshop,
            template_type=TermTemplateType.VEHICLE_RECEIPT,
            name="Recebimento A",
            document_title="TERMO A",
            is_default=True,
            content={"sections": [{"title": "P1", "topics": []}]},
        )
        self.term_b = WorkshopTermTemplate.objects.create(
            workshop=self.workshop,
            template_type=TermTemplateType.VEHICLE_RECEIPT,
            name="Recebimento B",
            document_title="TERMO B",
            content={"sections": [{"title": "P2", "topics": []}]},
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date="2026-08-30", number=1, slider=0)

    def test_step2_form_lists_active_terms(self) -> None:
        form = BudgetStep2Form(instance=self.budget, workshop=self.workshop)
        self.assertIn("term_template", form.fields)
        choice_values = {value for value, _label in form.fields["term_template"].choices if value}
        self.assertIn(str(self.term_a.pk), choice_values)
        self.assertIn(str(self.term_b.pk), choice_values)

    def test_update_budget_term_template_persists_selection(self) -> None:
        signing = update_budget_term_template(budget=self.budget, term_template_id=self.term_b.pk)
        assert signing is not None
        self.assertEqual(signing.term_template_id, self.term_b.pk)

    def test_locked_signing_blocks_term_change(self) -> None:
        signing = BudgetTermSigning.objects.create(budget=self.budget, term_template=self.term_a)
        signing.mark_signature_sent("env-1", document_id="env-1")
        signing = update_budget_term_template(budget=self.budget, term_template_id=self.term_b.pk)
        assert signing is not None
        self.assertEqual(signing.term_template_id, self.term_a.pk)
        self.assertEqual(signing.signature_request_status, SignatureStatus.SENT)
