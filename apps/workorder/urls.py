from django.urls import path
from . import views

app_name = "workorder"


urlpatterns = [
    path("", views.WorkOrderListView.as_view(), name="workorder_list"),
    path("status-report/pdf/preview/", views.WorkOrderStatusReportPdfPreviewView.as_view(), name="status_report_pdf_preview"),
    path("status-report/pdf/", views.WorkOrderStatusReportPdfView.as_view(), name="status_report_pdf"),
    path("<int:pk>/", views.WorkOrderDetailView.as_view(), name="workorder_detail"),
    path("<int:pk>/resume-section/", views.WorkOrderResumeSectionView.as_view(), name="resume_section"),
    path("<int:pk>/update-collaborators/", views.UpdateWorkOrderCollaboratorsView.as_view(), name="update_collaborators"),
    path("<int:pk>/allocation/", views.UpdateWorkOrderCommissionAllocationView.as_view(), name="update_allocation"),
    path("<int:pk>/payment-section/", views.WorkOrderPaymentSectionView.as_view(), name="payment_section"),
    path("<int:pk>/update-discount/", views.UpdateWorkOrderDiscountView.as_view(), name="update_discount"),
    path("<int:pk>/update-km-final/", views.UpdateWorkOrderKmFinalView.as_view(), name="update_km_final"),
    path("<int:pk>/update-delivery-date/", views.UpdateWorkOrderDeliveryDateView.as_view(), name="update_delivery_date"),
    path("<int:pk>/warranty-origin-detail/", views.WorkOrderWarrantyOriginDetailView.as_view(), name="warranty_origin_detail"),
    path("<int:pk>/update-observation/", views.UpdateWorkOrderObservationView.as_view(), name="update_observation"),
    path("<int:pk>/emission/continue/", views.WorkOrderEmissionContinueView.as_view(), name="emission_continue"),
    path("<int:pk>/reopen/", views.ReopenWorkOrderView.as_view(), name="reopen"),
    path("<int:pk>/kit/<int:item_id>/edit/", views.WorkOrderKitEditView.as_view(), name="edit_kit"),
    path("<int:pk>/status/<str:status>/", views.UpdateWorkOrderStatusView.as_view(), name="update_status"),
    # Items
    path("<int:pk>/items/modal/", views.WorkOrderEditItemsModalView.as_view(), name="edit_items_modal"),
    path("<int:pk>/items/selection/<str:item_type>/", views.WorkOrderItemSelectionModalView.as_view(), name="item_selection"),
    path("<int:pk>/items/add/<str:item_type>/", views.WorkOrderAddItemsBatchView.as_view(), name="add_items_batch"),
    path("<int:pk>/item/<int:item_id>/edit/", views.WorkOrderItemUpdateView.as_view(), name="edit_item"),
    path("<int:pk>/item/<int:item_id>/remove/", views.WorkOrderRemoveItemView.as_view(), name="remove_item"),
    # Payment
    path("add_payment/<int:pk>/", views.AddPaymentMethodView.as_view(), name="add_payment"),
    path("delete_payment/<int:pk>/", views.DeletePaymentMethodView.as_view(), name="delete_payment"),
    # Attachment
    path("attachment/<int:pk>/upload/", views.UploadAttachmentView.as_view(), name="upload_attachment"),
    path("attachment/<int:pk>/view/", views.ViewAttachmentView.as_view(), name="view_attachment"),
    path("attachment/<int:pk>/delete/", views.DeleteAttachmentView.as_view(), name="delete_attachment"),
    # PDF
    path("<int:pk>/visualizar-pdf/", views.visualizar_pdf_workorder, name="visualizar_pdf"),
    path("signature-preview/<str:token>/", views.signature_preview, name="signature_preview"),
    path("signature-file/<str:token>/", views.signature_file, name="signature_file"),
    path("<int:pk>/send-signature/", views.send_workorder_signature, name="send_signature"),
]
