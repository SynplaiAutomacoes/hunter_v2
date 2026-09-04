from django.urls import path
from . import views

app_name = "stock"

urlpatterns = [
    path("", views.StockImportListView.as_view(), name="stock_list"),
    path("report/", views.StockReportListView.as_view(), name="report"),
    path("report/pdf/preview/", views.StockReportPdfPreviewView.as_view(), name="report_pdf_preview"),
    path("report/pdf/", views.StockReportPdfView.as_view(), name="report_pdf"),
    path("report/excel/", views.StockReportExcelView.as_view(), name="report_excel"),
    path("history/<str:record_type>/<int:pk>/edit/", views.StockHistoryEditRedirectView.as_view(), name="history_edit"),
    path("alerts/", views.StockAlertsListView.as_view(), name="alerts"),
    path("movements/", views.StockMovementListView.as_view(), name="movements"),
    path("inquiry/", views.StockInquiryListView.as_view(), name="stock_inquiry"),
    path("replenishment/", views.ReplenishmentListView.as_view(), name="replenishment"),
    path("approvals/", views.MovementApprovalListView.as_view(), name="approvals"),
    path("approvals/<int:pk>/process/", views.MovementApprovalActionView.as_view(), name="process_approval"),
    path("import/", views.StockImportCreateView.as_view(), name="import"),
    path("transfer/", views.StockTransferCreateView.as_view(), name="transfer"),
    # Stock
    path("stock_update/<int:pk>", views.StockImportUpdateView.as_view(), name="stock_update"),
    path("transfer_update/<int:pk>", views.StockTransferUpdateView.as_view(), name="transfer_update"),
    path("stock_update/<int:pk>/refresh-sefaz/", views.RefreshSefazListView.as_view(), name="refresh_sefaz"),
    path("stock_delete/<int:pk>", views.StockImportDeleteView.as_view(), name="stock_delete"),
    path("stock_update/<int:pk>/nota-fiscal/", views.StockImportFiscalPreviewView.as_view(), name="fiscal_preview"),
    path("stock_xml_download/<int:pk>", views.StockImportXmlDownloadView.as_view(), name="xml_download"),
    path("stock_xml_bulk_download/", views.StockImportXmlArchiveDownloadView.as_view(), name="xml_bulk_download"),
    # Payment
    path("remove_payment_session/<int:payment_id>/", views.RemovePaymentSessionView.as_view(), name="remove_payment_session"),
    path("add_payment_session/", views.AddPaymentSessionView.as_view(), name="add_payment_session"),
    path("payment/additional/modal/", views.AdditionalChargeModalView.as_view(), name="add_additional_value_modal"),
    path("payment/additional/add/", views.AddAdditionalChargeSessionView.as_view(), name="add_additional_value_session"),
    # Link / Unlink
    path("link-manual/", views.LinkProductManualView.as_view(), name="link_product_manual"),
    path("link-manual/item-editor/", views.ManualLinkItemEditorView.as_view(), name="manual_link_item_editor"),
    path("unlink-item/", views.UnlinkItemView.as_view(), name="unlink_item"),
    #
    path("supplier_details/", views.SupplierDetailsView.as_view(), name="supplier_details"),
    path("update-manual-item-data/<int:pk>/", views.UpdateManualItemDataView.as_view(), name="update_manual_item_data"),
    # Transfer
    path("transfer/source-picker/", views.TransferSourceProductPickerView.as_view(), name="transfer_source_item_picker"),
    path("transfer/source-search/", views.TransferSourceProductSearchView.as_view(), name="transfer_source_product_search"),
    path("transfer/add-source-item/", views.AddTransferSourceItemView.as_view(), name="add_transfer_source_item"),
    path("transfer/destination-link/", views.TransferDestinationLinkView.as_view(), name="transfer_destination_link"),
    path("transfer/destination-search/", views.TransferDestinationProductSearchView.as_view(), name="transfer_destination_product_search"),
    path("transfer/create-destination-product/", views.CreateTransferDestinationProductView.as_view(), name="create_transfer_destination_product"),
    path("transfer/unlink-destination/", views.TransferUnlinkDestinationView.as_view(), name="transfer_unlink_destination"),
    path("transfer/remove-item/", views.RemoveTransferItemView.as_view(), name="remove_transfer_item"),
    path("transfer/update-item-data/<int:pk>/", views.UpdateTransferItemDataView.as_view(), name="update_transfer_item_data"),
    path("transfer/update-transfer-reason/<int:pk>", views.update_transfer_reason, name="update_transfer_reason"),
    # Quick Forms
    path("stock_product_search/", views.StockProductSearchView.as_view(), name="stock_product_search"),
    path("products/quick-create/", views.ProductQuickCreateView.as_view(), name="product_quick_create"),
    path("groups/quick-create/", views.CatalogGroupQuickCreateView.as_view(), name="group_quick_create"),
    path("supplier/quick-create/", views.SupplierQuickCreateView.as_view(), name="supplier_quick_create"),
    path("supplier/quick-update/<int:pk>/", views.SupplierQuickUpdateView.as_view(), name="supplier_quick_update"),
]
