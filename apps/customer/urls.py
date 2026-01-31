from django.urls import path
from . import views

app_name = "customer"


urlpatterns = [
    path("", views.CustomerListView.as_view(), name="customer_list"),
    path("create/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("<int:pk>/delete/", views.CustomerDeleteView.as_view(), name="customer_delete"),
    path("add-vehicle-form/", views.AddVehicleFormView.as_view(), name="add-vehicle-form"),
    path("history/", views.CustomerHistoryListView.as_view(), name="customer_history_list"),
    path("<int:pk>/history/", views.CustomerHistoryDetailView.as_view(), name="customer_history_detail"),
    path("vehicle/<int:pk>/history/", views.VehicleHistoryDetailView.as_view(), name="vehicle_history_detail"),
    path("<int:pk>/customer_pdf/", views.CustomerPDFView.as_view(), name="customer_pdf")
]
