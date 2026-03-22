from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.quote.models.investigative_questions import InvestigativeQuestion
from apps.quote.views.investigative_questions import InvestigativeQuestionListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Quote {suffix}",
        cnpj=f"35.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class InvestigativeQuestionListViewFilterTests(TestCase):
    def test_question_list_hides_inactive_by_default_but_allows_explicit_filters(self) -> None:
        workshop = create_workshop(suffix=1)
        active_question = InvestigativeQuestion.objects.create(workshop=workshop, text="Pergunta ativa", is_active=True)
        inactive_question = InvestigativeQuestion.objects.create(workshop=workshop, text="Pergunta inativa", is_active=False)
        factory = RequestFactory()

        default_view = InvestigativeQuestionListView()
        default_view.request = factory.get("/quote/investigative-questions/")
        default_view.workshop = workshop
        default_queryset = default_view.get_queryset()

        inactive_view = InvestigativeQuestionListView()
        inactive_view.request = factory.get("/quote/investigative-questions/", {"is_active": "0"})
        inactive_view.workshop = workshop
        inactive_queryset = inactive_view.get_queryset()

        all_view = InvestigativeQuestionListView()
        all_view.request = factory.get("/quote/investigative-questions/", {"is_active": "all"})
        all_view.workshop = workshop
        all_queryset = all_view.get_queryset()

        self.assertIn(active_question, default_queryset)
        self.assertNotIn(inactive_question, default_queryset)
        self.assertNotIn(active_question, inactive_queryset)
        self.assertIn(inactive_question, inactive_queryset)
        self.assertIn(active_question, all_queryset)
        self.assertIn(inactive_question, all_queryset)
