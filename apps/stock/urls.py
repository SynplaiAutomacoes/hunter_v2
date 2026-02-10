from django.urls import path
from . import views

app_name = "stock"

urlpatterns = [
    path('alerts/', views.StockAlertsListView.as_view(), name='alerts'),
    path('movements/', views.StockMovementListView.as_view(), name='movements'),
    path('replenishment/', views.ReplenishmentListView.as_view(), name='replenishment'),
    path('approvals/', views.MovementApprovalListView.as_view(), name='approvals'),
    path('approvals/<int:pk>/process/', views.MovementApprovalActionView.as_view(), name='process_approval'),
    path('import/', views.StockImportView.as_view(), name='import'),
    path('remove_payment_session/<int:payment_id>/', views.remove_payment_session, name='remove_payment_session'),
    path('add_payment_session/', views.add_payment_session, name='add_payment_session'),
]