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
]