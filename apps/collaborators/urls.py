from django.urls import path

from apps.collaborators.views import CollaboratorPayrollMarkPaidView, CollaboratorPayrollReceiptView, WorkshopCollaboratorCreateView, WorkshopCollaboratorDeleteView, WorkshopCollaboratorListView, WorkshopCollaboratorModalCreateView, WorkshopCollaboratorModalUpdateView, WorkshopCollaboratorUpdateView

app_name = "collaborators"


urlpatterns = [
    path("", WorkshopCollaboratorListView.as_view(), name="collaborator_list"),
    path("create/", WorkshopCollaboratorCreateView.as_view(), name="collaborator_create"),
    path("<int:pk>/edit/", WorkshopCollaboratorUpdateView.as_view(), name="collaborator_update"),
    path("<int:pk>/payroll/<int:payroll_id>/mark-paid/", CollaboratorPayrollMarkPaidView.as_view(), name="collaborator_payroll_mark_paid"),
    path("<int:pk>/payroll/<int:payroll_id>/receipt/", CollaboratorPayrollReceiptView.as_view(), name="collaborator_payroll_receipt"),
    path("<int:pk>/delete/", WorkshopCollaboratorDeleteView.as_view(), name="collaborator_delete"),
    path("create/modal/", WorkshopCollaboratorModalCreateView.as_view(), name="collaborator_create_modal"),
    path("update/modal/<int:pk>/", WorkshopCollaboratorModalUpdateView.as_view(), name="collaborator_update_modal"),
]
