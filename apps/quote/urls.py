from django.urls import path

from apps.quote.views.investigative_questions import (
    InvestigativeQuestionListView,
    InvestigativeQuestionCreateView,
    InvestigativeQuestionUpdateView,
    InvestigativeQuestionDeleteView,
)

app_name = "quote"

urlpatterns = [
    path("investigative-questions/", InvestigativeQuestionListView.as_view(), name="investigative_question_list"),
    path("investigative-questions/create/", InvestigativeQuestionCreateView.as_view(), name="investigative_question_create"),
    path("investigative-questions/<int:pk>/edit/", InvestigativeQuestionUpdateView.as_view(), name="investigative_question_update"),
    path("investigative-questions/<int:pk>/delete/", InvestigativeQuestionDeleteView.as_view(), name="investigative_question_delete"),
]
