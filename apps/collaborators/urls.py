from django.urls import path

from apps.collaborators.views import WorkshopCollaboratorListView, WorkshopCollaboratorUpdateView, WorkshopCollaboratorCreateView, WorkshopCollaboratorDeleteView

app_name = "collaborators"


urlpatterns = [
    path("", WorkshopCollaboratorListView.as_view(), name="collaborator_list"),
    path("create/", WorkshopCollaboratorCreateView.as_view(), name="collaborator_create"),
    path("<int:pk>/edit/", WorkshopCollaboratorUpdateView.as_view(), name="collaborator_update"),
    path("<int:pk>/delete/", WorkshopCollaboratorDeleteView.as_view(), name="collaborator_delete"),
]
