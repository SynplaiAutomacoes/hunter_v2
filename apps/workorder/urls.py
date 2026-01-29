from django.urls import path
from . import views

app_name = "workorder"


urlpatterns = [
    path("", views.WorkOrderListView.as_view(), name="workorder_list"),
    path("<int:pk>/", views.WorkOrderDetailView.as_view(), name="workorder_detail"),
    path("add_payment/<int:pk>/", views.add_payment_method, name="add_payment"),
    path("delete_payment/<int:pk>/", views.delete_payment_method, name="delete_payment"),
]