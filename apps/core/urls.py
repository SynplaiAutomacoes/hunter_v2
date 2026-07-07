from django.urls import path
from apps.core.presentation import views

app_name = "core"

urlpatterns = [
    path("cep-lookup/", views.CEPLookupView.as_view(), name="cep_lookup"),
    path("navbar-favorites/toggle/", views.FavoritePageToggleView.as_view(), name="favorite_page_toggle"),
    path("navbar-favorites/reorder/", views.FavoritePageReorderView.as_view(), name="favorite_page_reorder"),
    path("dashboard/financial-report/modal/", views.DashboardFinancialReportModalView.as_view(), name="dashboard_financial_report_modal"),
    path("dashboard/financial-report/", views.DashboardFinancialReportView.as_view(), name="dashboard_financial_report"),
    path("lock/acquire/", views.AcquireLockView.as_view(), name="lock_acquire"),
    path("lock/release/", views.ReleaseLockView.as_view(), name="lock_release"),
    path("lock/refresh/", views.RefreshLockView.as_view(), name="lock_refresh"),
    path("lock/check/", views.CheckLockView.as_view(), name="lock_check"),
    path("", views.DashboardView.as_view(), name="dashboard"),
]
