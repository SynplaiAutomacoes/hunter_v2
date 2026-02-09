from django.urls import path
from . import views

app_name = "stock"

urlpatterns = [
    path('alerts/', views.StockAlertsListView.as_view(), name='alerts'),
]