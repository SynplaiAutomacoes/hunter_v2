from django.urls import path
from . import views

app_name = "customer"


urlpatterns = [
    # Customer
    path("", views.CustomerListView.as_view(), name="customer_list"),
    path("create/", views.CustomerCreateView.as_view(), name="customer_create"),
    path(
        "disable-all-messaging/",
        views.CustomerDisableAllMessagingView.as_view(),
        name="disable_all_messaging",
    ),
    path("<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("<int:pk>/delete/", views.CustomerDeleteView.as_view(), name="customer_delete"),
    # History
    path("history/", views.CustomerHistoryListView.as_view(), name="customer_history_list"),
    path("<int:pk>/history/", views.CustomerHistoryDetailView.as_view(), name="customer_history_detail"),
    path("vehicle/<int:pk>/history/", views.VehicleHistoryDetailView.as_view(), name="vehicle_history_detail"),
    # Vehicle
    path("add-vehicle-form/", views.AddVehicleFormView.as_view(), name="add-vehicle-form"),
    path("check-plate/<str:plate>/", views.api_check_plate, name="check-plate"),
    path("vehicle-catalog/brands/", views.api_vehicle_catalog_brands, name="vehicle-catalog-brands"),
    path("vehicle-catalog/models/", views.api_vehicle_catalog_models, name="vehicle-catalog-models"),
    path("vehicle-catalog/fuels/", views.api_vehicle_catalog_fuels, name="vehicle-catalog-fuels"),
    # Quick Forms
    path("quick-create/", views.QuickCustomerCreateView.as_view(), name="quick_create"),
    path("quick-update/<int:pk>/", views.QuickCustomerUpdateView.as_view(), name="quick_update"),
    path("vehicle/quick-create/", views.QuickVehicleCreateView.as_view(), name="vehicle_quick_create"),
    path("vehicle/quick-update/<int:pk>/", views.QuickVehicleUpdateView.as_view(), name="vehicle_quick_update"),
]
