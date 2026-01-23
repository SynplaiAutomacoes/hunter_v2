from django.urls import path
from . import views

app_name = "customer"


urlpatterns = [
    path("", views.CustomerListView.as_view(), name="customer_list"),
    path("create/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("<int:pk>/delete/", views.CustomerDeleteView.as_view(), name="customer_delete"),
    path("add-vehicle-form/", views.AddVehicleFormView.as_view(), name="add-vehicle-form"),
    path("customer-detail/", views.customer_detail, name="customer-detail"),
    path("vehicle-detail/", views.vehicle_detail, name="vehicle-detail"),
    path("get-vehicles/", views.get_vehicles, name="vehicle-detail"),
]
