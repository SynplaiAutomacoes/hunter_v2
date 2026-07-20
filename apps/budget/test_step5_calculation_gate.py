from __future__ import annotations

from datetime import date

from django.test import RequestFactory, TestCase

from apps.budget.forms.presenters.step5_context import build_step5_context
from apps.budget.models import Budget, BudgetStatus
from apps.budget.views.shared import reset_steps_after_step_4
from apps.budget.views.workflow_views import BudgetUpdateView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Step5 {suffix}",
        cnpj=f"66.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
        uf="SP",
    )


class Step5CalculationGateTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop()

    def test_build_step5_context_marks_calculation_done_when_viewed(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 20),
            current_step=5,
            step5_calculation_viewed=True,
        )

        context = build_step5_context(budget)

        self.assertTrue(context.step5_calculation_done)
        self.assertEqual(context.step5_calculated_input_value, "1")
        self.assertEqual(context.step5_should_block_next_button, "false")

    def test_reset_steps_after_step_4_clears_calculation_viewed(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 20),
            current_step=6,
            step5_calculation_viewed=True,
        )

        reset_steps_after_step_4(budget)
        budget.refresh_from_db()

        self.assertEqual(budget.current_step, 4)
        self.assertFalse(budget.step5_calculation_viewed)
        context = build_step5_context(budget)
        self.assertFalse(context.step5_calculation_done)
        self.assertEqual(context.step5_calculated_input_value, "0")

    def test_is_step5_calculation_done_when_viewed_at_step_five(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 20),
            status=BudgetStatus.DRAFT,
            current_step=5,
            step5_calculation_viewed=True,
        )
        request = self.factory.get(f"/budget/{budget.pk}/edit/?step=5")
        request.session = self.client.session
        view = BudgetUpdateView()
        view.request = request
        view.kwargs = {"pk": budget.pk}
        view.workshop = self.workshop
        view.object = budget

        self.assertTrue(view._is_step5_calculation_done())
