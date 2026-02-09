from django.urls import path
from . import views

app_name = "stock"

urlpatterns = [
    path('alerts/', views.StockAlertsListView.as_view(), name='alerts'),
    path('movements/', views.StockMovementListView.as_view(), name='movements'),
    path('replenishment/', views.ReplenishmentListView.as_view(), name='replenishment'),
]