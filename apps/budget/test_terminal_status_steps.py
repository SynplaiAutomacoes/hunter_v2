from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.budget.models import Budget, BudgetStatus
from apps.budget.views.workflow_views import BudgetUpdateView
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Terminal Steps {suffix}",
        cnpj=f"55.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
        uf="SP",
    )


class BudgetTerminalStatusStepAccessTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop()
        self.user = User.objects.create_user(username="budget-terminal-steps", password="test", cpf="12345678903")

    def _build_view(self, *, budget: Budget, step: int | None = None) -> BudgetUpdateView:
        path = f"/budget/{budget.pk}/edit/"
        if step is not None:
            path = f"{path}?step={step}"
        request = self.factory.get(path)
        request.user = self.user
        request.session = self.client.session
        view = BudgetUpdateView()
        view.request = request
        view.kwargs = {"pk": budget.pk}
        view.workshop = self.workshop
        view.object = budget
        return view

    def test_terminal_statuses_expose_all_six_steps(self) -> None:
        cases = [
            (BudgetStatus.APPROVED, 3),
            (BudgetStatus.REJECTED, 4),
            (BudgetStatus.CANCELLED, 2),
        ]
        for status, current_step in cases:
            with self.subTest(status=status, current_step=current_step):
                budget = Budget.objects.create(
                    workshop=self.workshop,
                    entry_date=date(2026, 7, 20),
                    status=status,
                    current_step=current_step,
                )
                view = self._build_view(budget=budget, step=current_step)
                context = view.get_context_data()
                self.assertEqual(context["max_reached_step"], 6)

    def test_draft_budget_keeps_current_step_as_max_reached(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 20),
            status=BudgetStatus.DRAFT,
            current_step=3,
        )
        view = self._build_view(budget=budget, step=3)
        context = view.get_context_data()
        self.assertEqual(context["max_reached_step"], 3)

    def test_opening_locked_budget_redirects_to_step_six(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 20),
            status=BudgetStatus.APPROVED,
            current_step=3,
        )
        view = self._build_view(budget=budget)
        response = view.get(view.request, pk=budget.pk)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/budget/{budget.pk}/edit/?step=6", response["Location"])

    def test_opening_draft_budget_redirects_to_current_step(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 20),
            status=BudgetStatus.DRAFT,
            current_step=3,
        )
        view = self._build_view(budget=budget)
        response = view.get(view.request, pk=budget.pk)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/budget/{budget.pk}/edit/?step=3", response["Location"])
