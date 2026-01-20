from django.urls import path
from apps.suppliers.views import (
    SupplierListView,
    SupplierCreateView,
    SupplierUpdateView,
    SupplierDeleteView,
)

app_name = "suppliers"

urlpatterns = [
    path("", SupplierListView.as_view(), name="supplier_list"),
    path("create/", SupplierCreateView.as_view(), name="supplier_create"),
    path("<int:pk>/edit/", SupplierUpdateView.as_view(), name="supplier_update"),
    path("<int:pk>/delete/", SupplierDeleteView.as_view(), name="supplier_delete"),
]