from django.urls import path
from . import views

app_name = "workorder"


urlpatterns = [
    path("", views.WorkOrderListView.as_view(), name="workorder_list"),
    path("<int:pk>/", views.WorkOrderDetailView.as_view(), name="workorder_detail"),
    path("add_payment/<int:pk>/", views.AddPaymentMethodView.as_view(), name="add_payment"),
    path("delete_payment/<int:pk>/", views.DeletePaymentMethodView.as_view(), name="delete_payment"),
]