from django.urls import path
from . import views

app_name = "budget"

urlpatterns = [
    path("", views.BudgetListView.as_view(), name="budget_list"),
    path("create/", views.BudgetCreateView.as_view(), name="budget_create"),
    path("<int:pk>/edit/", views.BudgetUpdateView.as_view(), name="budget_update"),
    path("<int:pk>/delete/", views.BudgetDeleteView.as_view(), name="budget_delete"),
    path('product_selection/<int:budget_id>/', views.product_selection_modal, name='product_selection'),
    path('service_selection/<int:budget_id>/', views.service_selection_modal, name='service_selection'),
    path("<int:budget_id>/add-product/<int:product_id>/", views.add_product_to_budget, name="add_product_to_budget"),
    path("<int:budget_id>/add-service/<int:service_id>/", views.add_service_to_budget, name="add_service_to_budget"),
]