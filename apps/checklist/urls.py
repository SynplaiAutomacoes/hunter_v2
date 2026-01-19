from django.urls import path
from .views import (
    ChecklistListView,
    ChecklistCreateView,
    ChecklistUpdateView,
    ChecklistDeleteView,
)

app_name = "checklist"

urlpatterns = [
    path("", ChecklistListView.as_view(), name="checklist_list"),
    path("create/", ChecklistCreateView.as_view(), name="checklist_create"),
    path("<int:pk>/edit/", ChecklistUpdateView.as_view(), name="checklist_update"),
    path("<int:pk>/delete/", ChecklistDeleteView.as_view(), name="checklist_delete"),
]