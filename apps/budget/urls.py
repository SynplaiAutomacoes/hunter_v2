from django.urls import path
from . import views

app_name = "budget"

urlpatterns = [
    path("", views.BudgetListView.as_view(), name="budget_list"),
    path("create/", views.BudgetCreateView.as_view(), name="budget_create"),
    path("<int:pk>/edit/", views.BudgetUpdateView.as_view(), name="budget_update"),
    path("<int:pk>/delete/", views.BudgetDeleteView.as_view(), name="budget_delete"),

    path("customer-detail/", views.CustomerDetailView.as_view(), name="customer-detail"),
    path("vehicle-detail/", views.VehicleDetailView.as_view(), name="vehicle-detail"),
    path("get-vehicles/", views.VehicleListView.as_view(), name="get-vehicles"),

    path("selection/<int:budget_id>/<str:item_type>/", views.ItemSelectionModalView.as_view(), name="item_selection"),
    path("<int:budget_id>/add-item/<int:item_id>/<str:item_type>/", views.AddItemToBudgetView.as_view(), name="add_item_to_budget"),
    path("<int:budget_id>/remove-item/<int:item_id>/<str:item_type>/", views.RemoveItemFromBudgetView.as_view(), name="remove_item_from_budget"),
    path('<int:budget_id>/remove-budget-item/<int:item_id>/', views.RemoveBudgetItemView.as_view(), name='remove_budget_item'),
    path('<int:budget_id>/item/<int:item_id>/edit/', views.BudgetItemUpdateView.as_view(), name='edit_item'),
    path('<int:budget_id>/item/<int:item_id>/calculate/', views.BudgetItemCalculateView.as_view(), name='calculate_item'),

    path("update_slider/<int:budget_id>/", views.UpdateSliderView.as_view(), name="update_slider"),
    path("update-budget-discount/<int:budget_id>/", views.UpdateBudgetDiscountView.as_view(), name="update_budget_discount"),
    path("update-status/<int:budget_id>/<str:status>", views.UpdateBudgetStatusView.as_view(), name="update_budget_status"),

    path("save-observation/", views.SaveObservationView.as_view(), name="save_observation"),
    path("image-view/<int:pk>", views.BudgetImageView.as_view(), name="image_view"),
    path("<int:budget_id>/add-items-batch/<str:item_type>/", views.AddItemsBatchToBudgetView.as_view(), name="add_items_batch"),
    path("<int:budget_id>/summary/", views.BudgetSummaryView.as_view(), name="budget_summary"),
    path("<int:budget_id>/collaborator-field/", views.BudgetStep3CollaboratorFieldView.as_view(), name="collaborator_field"),

    # Local items URLs
    path('<int:budget_id>/create-local/<str:item_type>/', views.CreateLocalItemView.as_view(), name='create_local_item'),
    path('<int:budget_id>/register-local/<int:item_id>/', views.RegisterLocalItemView.as_view(), name='register_local_item'),
    path('<int:budget_id>/calculate-local-service/', views.CalculateLocalServiceView.as_view(), name='calculate_local_service'),
    path('<int:budget_id>/quick-create/<str:item_type>/', views.QuickCreateProductView.as_view(), name='quick_create_item'),
]