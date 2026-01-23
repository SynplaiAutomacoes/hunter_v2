from django.urls import path
from . import views

app_name = "budget"

urlpatterns = [
    path("", views.BudgetListView.as_view(), name="budget_list"),
    path("create/", views.BudgetCreateView.as_view(), name="budget_create"),
    path("delete/", views.BudgetDeleteView.as_view(), name="budget_delete"),
]