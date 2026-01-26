from django.urls import path
from . import views

app_name = "checklist"

urlpatterns = [
    path("", views.ChecklistListView.as_view(), name="checklist_list"),
    path("create/", views.ChecklistCreateView.as_view(), name="checklist_create"),
    path("<int:pk>/edit/", views.ChecklistUpdateView.as_view(), name="checklist_update"),
    path("<int:pk>/delete/", views.ChecklistDeleteView.as_view(), name="checklist_delete"),
    path("add_item_row/", views.AddChecklistItemRowView.as_view(), name="add_item_row"),
]