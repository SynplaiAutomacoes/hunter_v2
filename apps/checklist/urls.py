from django.urls import path
from .views import (
    ChecklistListView,
    ChecklistCreateView,
    ChecklistUpdateView,
    ChecklistDeleteView,
    add_checklist_item_row,
)

app_name = "checklist"

urlpatterns = [
    path("", ChecklistListView.as_view(), name="checklist_list"),
    path("create/", ChecklistCreateView.as_view(), name="checklist_create"),
    path("<int:pk>/edit/", ChecklistUpdateView.as_view(), name="checklist_update"),
    path("<int:pk>/delete/", ChecklistDeleteView.as_view(), name="checklist_delete"),
    path("add_item_row/", add_checklist_item_row, name="add_item_row"),
]