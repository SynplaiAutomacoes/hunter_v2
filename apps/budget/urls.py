from django.urls import path
from . import views

app_name = "budget"

urlpatterns = [
    path("", views.BudgetListView.as_view(), name="budget_list"),
    path("create/", views.BudgetCreateView.as_view(), name="budget_create"),
    path("<int:pk>/edit/", views.BudgetUpdateView.as_view(), name="budget_update"),
    path("<int:pk>/delete/", views.BudgetDeleteView.as_view(), name="budget_delete"),
    path("selection/<int:budget_id>/<str:item_type>/", views.item_selection_modal, name="item_selection"),
    path("<int:budget_id>/add-item/<int:item_id>/<str:item_type>/", views.add_item_to_budget, name="add_item_to_budget"),
    path("<int:budget_id>/remove-item/<int:item_id>/<str:item_type>/", views.remove_item_from_budget, name="remove_item_from_budget"),
    path("update-budget-discount/<int:budget_id>/", views.update_budget_discount, name="update_budget_discount"),
    path("save-observation/", views.save_observation, name="save_observation"),
    path("update-status/<int:budget_id>/<str:status>", views.update_budget_status, name="update_budget_status"),
]