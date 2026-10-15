from django.urls import path

from apps.core.presentation import views
from apps.core.presentation import management_report_views
from apps.core.presentation import data_import_views

app_name = "core"

urlpatterns = [
    path("import/history/", data_import_views.DataImportHistoryView.as_view(), name="data_import_history"),
    path("import/history/<int:batch_id>/", data_import_views.DataImportHistoryDetailView.as_view(), name="data_import_history_detail"),
    path("import/history/<int:batch_id>/rollback/", data_import_views.DataImportRollbackModalView.as_view(), name="data_import_rollback_modal"),
    path("import/history/<int:batch_id>/rollback/execute/", data_import_views.DataImportRollbackExecuteView.as_view(), name="data_import_rollback_execute"),
    path("import/<str:entity>/", data_import_views.DataImportModalView.as_view(), name="data_import_modal"),
    path("import/<str:entity>/example/", data_import_views.DataImportExampleModalView.as_view(), name="data_import_example"),
    path("import/<str:entity>/upload/", data_import_views.DataImportUploadView.as_view(), name="data_import_upload"),
    path("import/<str:entity>/confirm/", data_import_views.DataImportConfirmView.as_view(), name="data_import_confirm"),
    path("import/<str:entity>/execute/", data_import_views.DataImportExecuteView.as_view(), name="data_import_execute"),
    path("cep-lookup/", views.CEPLookupView.as_view(), name="cep_lookup"),
    path("navbar-favorites/toggle/", views.FavoritePageToggleView.as_view(), name="favorite_page_toggle"),
    path("navbar-favorites/reorder/", views.FavoritePageReorderView.as_view(), name="favorite_page_reorder"),
    path("dashboard/financial-report/modal/", views.DashboardFinancialReportModalView.as_view(), name="dashboard_financial_report_modal"),
    path("dashboard/financial-report/excel/", views.DashboardFinancialReportExcelView.as_view(), name="dashboard_financial_report_excel"),
    path("dashboard/financial-report/", views.DashboardFinancialReportView.as_view(), name="dashboard_financial_report"),
    path("reports/", management_report_views.ReportsHubView.as_view(), name="reports_hub"),
    path("reports/view/", management_report_views.ManagementReportView.as_view(), name="management_report"),
    path("reports/pdf/", management_report_views.ManagementReportPdfView.as_view(), name="management_report_pdf"),
    path("reports/excel/", management_report_views.ManagementReportExcelView.as_view(), name="management_report_excel"),
    path("lock/acquire/", views.AcquireLockView.as_view(), name="lock_acquire"),
    path("lock/release/", views.ReleaseLockView.as_view(), name="lock_release"),
    path("lock/refresh/", views.RefreshLockView.as_view(), name="lock_refresh"),
    path("lock/check/", views.CheckLockView.as_view(), name="lock_check"),
    path("", views.DashboardView.as_view(), name="dashboard"),
]
