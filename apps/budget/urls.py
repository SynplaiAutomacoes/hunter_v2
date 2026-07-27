from django.urls import path
from . import views
from .views.workflow_views import BudgetReferenceModalView

app_name = "budget"

urlpatterns = [
    # 01. Fluxo principal do orcamento (lista, criacao, edicao e exclusao)
    path("", views.BudgetListView.as_view(), name="budget_list"),
    path("status-report/pdf/preview/", views.BudgetStatusReportPdfPreviewView.as_view(), name="status_report_pdf_preview"),
    path("status-report/pdf/", views.BudgetStatusReportPdfView.as_view(), name="status_report_pdf"),
    path("create/", views.BudgetCreateView.as_view(), name="budget_create"),
    path("<int:pk>/edit/", views.BudgetUpdateView.as_view(), name="budget_update"),
    path("<int:pk>/delete/", views.BudgetDeleteView.as_view(), name="budget_delete"),
    # 02. Eventos em tempo real
    path("events/", views.BudgetEventsView.as_view(), name="budget_events"),
    # 03. Cliente e veiculo (autocomplete e detalhes)
    path("customer-detail/", views.CustomerDetailView.as_view(), name="customer-detail"),
    path("vehicle-detail/", views.VehicleDetailView.as_view(), name="vehicle-detail"),
    path("get-vehicles/", views.VehicleListView.as_view(), name="get-vehicles"),
    path("check-open-budget/", views.BudgetCheckOpenBudgetView.as_view(), name="check_open_budget"),
    # 04. Itens do orcamento (selecao, adicao, remocao, edicao e calculo)
    path("selection/<int:budget_id>/<str:item_type>/", views.ItemSelectionModalView.as_view(), name="item_selection"),
    path("<int:budget_id>/add-item/<int:item_id>/<str:item_type>/", views.AddItemToBudgetView.as_view(), name="add_item_to_budget"),
    path("<int:budget_id>/add-items-batch/<str:item_type>/", views.AddItemsBatchToBudgetView.as_view(), name="add_items_batch"),
    path("<int:budget_id>/remove-item/<int:item_id>/<str:item_type>/", views.RemoveItemFromBudgetView.as_view(), name="remove_item_from_budget"),
    path("<int:budget_id>/remove-budget-item/<int:item_id>/", views.RemoveBudgetItemView.as_view(), name="remove_budget_item"),
    path("<int:budget_id>/remove-products-batch/", views.RemoveProductItemsBatchFromBudgetView.as_view(), name="remove_products_batch"),
    path("<int:budget_id>/remove-services-batch/", views.RemoveServiceItemsBatchFromBudgetView.as_view(), name="remove_services_batch"),
    path("<int:budget_id>/remove-kits-batch/", views.RemoveKitItemsBatchFromBudgetView.as_view(), name="remove_kits_batch"),
    path("<int:budget_id>/item/<int:item_id>/edit/", views.BudgetItemUpdateView.as_view(), name="edit_item"),
    path("<int:budget_id>/item/<int:item_id>/calculate/", views.BudgetItemCalculateView.as_view(), name="calculate_item"),
    # 05. Kits do orcamento (edicao e calculo de componentes)
    path("<int:budget_id>/kit/<int:item_id>/edit/", views.BudgetKitEditView.as_view(), name="edit_kit"),
    path("<int:budget_id>/kit/<int:item_id>/product/<int:product_id>/calculate/", views.BudgetKitProductCalculateView.as_view(), name="calculate_kit_product"),
    path("<int:budget_id>/kit/<int:item_id>/service/<int:service_id>/calculate/", views.BudgetKitServiceCalculateView.as_view(), name="calculate_kit_service"),
    # 06. Etapas e acoes do orcamento (slider, desconto, status e observacao)
    path("update_slider/<int:budget_id>/", views.UpdateSliderView.as_view(), name="update_slider"),
    path("mark-step5-calculation-viewed/<int:budget_id>/", views.MarkStep5CalculationViewedView.as_view(), name="mark_step5_calculation_viewed"),
    path("update-budget-discount/<int:budget_id>/", views.UpdateBudgetDiscountView.as_view(), name="update_budget_discount"),
    path("autosave-review-date/<int:budget_id>/", views.BudgetReviewDateAutosaveView.as_view(), name="autosave_review_date"),
    path("update-status/<int:budget_id>/<str:status>", views.UpdateBudgetStatusView.as_view(), name="update_budget_status"),  # sem barra final por compatibilidade
    path("save-observation/", views.SaveObservationView.as_view(), name="save_observation"),
    # 07. Assinatura do orcamento (envio e acesso por token)
    path("send-signature/<int:budget_id>/", views.SendBudgetSignatureView.as_view(), name="send_signature"),
    path("signature-preview/<str:token>/", views.signature_preview, name="signature_preview"),
    path("signature-file/<str:token>/", views.signature_file, name="signature_file"),
    # 08. Resumo e campos auxiliares da etapa
    path("<int:budget_id>/summary/", views.BudgetSummaryView.as_view(), name="budget_summary"),
    path("<int:budget_id>/collaborator-field/", views.BudgetStep3CollaboratorFieldView.as_view(), name="collaborator_field"),
    # 09. Arquivos e PDFs do orcamento (sem barra final por compatibilidade)
    path("image-view/<int:pk>", views.BudgetImageView.as_view(), name="image_view"),
    path("visualizar-pdf/<int:pk>", views.visualizar_pdf, name="visualizar_pdf"),
    path("visualizar-pdf-assinatura/<int:pk>", views.visualizar_pdf_assinatura, name="visualizar_pdf_assinatura"),
    path("visualizar-pdf-checklist/<int:pk>", views.visualizar_pdf_checklist, name="visualizar_pdf_checklist"),
    path("visualizar-pdf-gestor/<int:pk>", views.visualizar_pdf_gestor, name="visualizar_pdf_gestor"),
    path("download-pdf-gestor/<int:pk>", views.download_pdf_gestor, name="download_pdf_gestor"),
    path("visualizar-pdf-mecanico/<int:pk>", views.visualizar_pdf_mecanico, name="visualizar_pdf_mecanico"),
    # 10. Webhook SuperSign
    path("supersign/webhook/ping/", views.SuperSignWebhookView.as_view(), name="supersign_webhook_ping"),
    path("supersign/webhook/", views.SuperSignWebhookView.as_view(), name="supersign_webhook"),
    # 11. Itens locais e criacao rapida
    path("<int:budget_id>/create-local/<str:item_type>/", views.CreateLocalItemView.as_view(), name="create_local_item"),
    path("<int:budget_id>/register-local/<int:item_id>/", views.RegisterLocalItemView.as_view(), name="register_local_item"),
    path("<int:budget_id>/calculate-local-service/", views.CalculateLocalServiceView.as_view(), name="calculate_local_service"),
    path("<int:budget_id>/quick-create/<str:item_type>/", views.QuickCreateProductView.as_view(), name="quick_create_item"),
    path("<int:pk>/reference-modal/", BudgetReferenceModalView.as_view(), name="budget_reference_modal"),
    path("<int:pk>/link-modal/", views.BudgetLinkModalView.as_view(), name="budget_link_modal"),
    path("<int:pk>/link-search/", views.BudgetLinkSearchView.as_view(), name="budget_link_search"),
    path("<int:pk>/link/", views.BudgetLinkProcessView.as_view(), name="budget_link_process"),
    path("<int:pk>/unlink-modal/", views.BudgetUnlinkModalView.as_view(), name="budget_unlink_modal"),
    path("<int:pk>/unlink/", views.BudgetUnlinkProcessView.as_view(), name="budget_unlink_process"),
    path("<int:pk>/import-items-search-modal/", views.BudgetImportItemsSearchModalView.as_view(), name="import_items_search_modal"),
    path("<int:pk>/import-items-select-modal/", views.BudgetImportItemsSelectModalView.as_view(), name="import_items_select_modal"),
    path("<int:pk>/import-items-process/", views.BudgetImportItemsProcessView.as_view(), name="import_items_process"),
]
