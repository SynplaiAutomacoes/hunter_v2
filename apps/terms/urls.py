from django.urls import path

from apps.terms import views


app_name = "terms"

urlpatterns = [
    path("", views.WorkshopTermTemplateListView.as_view(), name="term_template_list"),
    path("create/", views.WorkshopTermTemplateCreateView.as_view(), name="term_template_create"),
    path("<int:pk>/edit/", views.WorkshopTermTemplateUpdateView.as_view(), name="term_template_update"),
    path("<int:pk>/delete/", views.WorkshopTermTemplateDeleteView.as_view(), name="term_template_delete"),
    path("<int:pk>/duplicate/", views.WorkshopTermTemplateDuplicateView.as_view(), name="term_template_duplicate"),
    path("<int:pk>/preview/", views.term_template_preview, name="term_template_preview"),
    path("budget/<int:budget_id>/preview/", views.budget_term_preview, name="budget_term_preview"),
    path("budget/<int:budget_id>/send-signature/", views.SendBudgetTermSignatureView.as_view(), name="budget_term_send_signature"),
    path("budget/signature-preview/<str:token>/", views.budget_term_signature_preview, name="budget_term_signature_preview"),
    path("budget/signature-file/<str:token>/", views.budget_term_signature_file, name="budget_term_signature_file"),
    path("workorder/<int:workorder_id>/preview/", views.workorder_term_preview, name="workorder_term_preview"),
    path("workorder/<int:workorder_id>/send-signature/", views.SendWorkOrderTermSignatureView.as_view(), name="workorder_term_send_signature"),
    path("workorder/signature-preview/<str:token>/", views.workorder_term_signature_preview, name="workorder_term_signature_preview"),
    path("workorder/signature-file/<str:token>/", views.workorder_term_signature_file, name="workorder_term_signature_file"),
]
