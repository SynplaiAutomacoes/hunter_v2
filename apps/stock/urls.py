from django.urls import path
from . import views

app_name = "stock"

urlpatterns = [
    path("", views.StockImportListView.as_view(), name="stock_list"),
    path("alerts/", views.StockAlertsListView.as_view(), name="alerts"),
    path("movements/", views.StockMovementListView.as_view(), name="movements"),
    path("replenishment/", views.ReplenishmentListView.as_view(), name="replenishment"),
    path("approvals/", views.MovementApprovalListView.as_view(), name="approvals"),
    path("approvals/<int:pk>/process/", views.MovementApprovalActionView.as_view(), name="process_approval"),
    path("import/", views.StockImportCreateView.as_view(), name="import"),
    #
    path("stock_update/<int:pk>", views.StockImportUpdateView.as_view(), name="stock_update"),
    path("stock_update/<int:pk>/refresh-sefaz/", views.RefreshSefazListView.as_view(), name="refresh_sefaz"),
    path("stock_delete/<int:pk>", views.StockImportDeleteView.as_view(), name="stock_delete"),
    path("remove_payment_session/<int:payment_id>/", views.RemovePaymentSessionView.as_view(), name="remove_payment_session"),
    path("add_payment_session/", views.AddPaymentSessionView.as_view(), name="add_payment_session"),
    path("link-manual/", views.LinkProductManualView.as_view(), name="link_product_manual"),
    path("unlink-item/", views.UnlinkItemView.as_view(), name="unlink_item"),
    path("supplier_details/", views.SupplierDetailsView.as_view(), name="supplier_details"),
    path("update-manual-item-data/<int:pk>/", views.UpdateManualItemDataView.as_view(), name="update_manual_item_data"),
    # Quick Create
    path("stock_product_search/", views.StockProductSearchView.as_view(), name="stock_product_search"),
    path("products/quick-create/", views.ProductQuickCreateView.as_view(), name="product_quick_create"),
    path("groups/quick-create/", views.CatalogGroupQuickCreateView.as_view(), name="group_quick_create"),
    path("supplier/quick-create/", views.SupplierQuickCreateView.as_view(), name="supplier_quick_create"),
]
