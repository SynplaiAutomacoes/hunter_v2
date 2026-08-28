from django.urls import path

from . import views

app_name = "terms"

urlpatterns = [
    path("", views.TermTemplateListView.as_view(), name="term_list"),
    path("create/", views.TermTemplateCreateView.as_view(), name="term_create"),
    path("<int:pk>/preview-modal/", views.TermTemplatePreviewModalView.as_view(), name="term_preview_modal"),
    path("<int:pk>/preview/", views.TermTemplatePreviewView.as_view(), name="term_preview"),
    path("<int:pk>/edit/", views.TermTemplateUpdateView.as_view(), name="term_update"),
    path("<int:pk>/delete/", views.TermTemplateDeleteView.as_view(), name="term_delete"),
    path("add-topic/", views.AddTermTopicView.as_view(), name="add_topic"),
    path("add-item/", views.AddTermItemView.as_view(), name="add_item"),
    path("budgets/<int:budget_id>/receipt/", views.BudgetTermModalView.as_view(), name="budget_term_modal"),
    path("budgets/<int:budget_id>/receipt/<int:template_id>/", views.BudgetTermModalView.as_view(), name="budget_term_modal_selected"),
    path("budgets/<int:budget_id>/receipt/<int:template_id>/preview/", views.BudgetTermPreviewView.as_view(), name="budget_term_preview"),
    path("budgets/<int:budget_id>/receipt/<int:template_id>/send/", views.BudgetTermSendView.as_view(), name="budget_term_send"),
    path("budgets/<int:budget_id>/receipt/<int:template_id>/signed/", views.BudgetTermSignedPdfView.as_view(), name="budget_term_signed"),
]
