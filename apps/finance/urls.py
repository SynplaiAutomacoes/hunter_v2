from django.urls import path
from django.views.generic import RedirectView

from apps.finance.views import (
    EmissionPreviewView,
    EmissionRequestCreateView,
    EmissionWorkOrderKitComponentUpdateView,
    EmissionWorkOrderItemUpdateView,
    FinancialGroupCreateView,
    FinancialGroupDeleteView,
    FinancialGroupListView,
    FinancialGroupUpdateView,
    NfeCreateRedirectView,
    NfeDocumentDownloadView,
    NfeRequestDetailView,
    NfeRequestListView,
    NfeRequestReconcileView,
    NfeRequestUpdateView,
    NfseCreateRedirectView,
    NfseDocumentDownloadView,
    NfseRequestDetailView,
    NfseRequestListView,
    NfseRequestUpdateView,
    TaxClassCreateView,
    TaxClassListView,
    TaxClassPresetCreateView,
    TaxClassPresetListView,
    TaxClassPresetUpdateView,
    TaxClassUpdateView,
    WebhookView,
    WebmaniaCompanyDetailView,
    WebmaniaCompanyListView,
    WebmaniaCompanySyncView,
    WebmaniaCompanyUpdateView,
)
from apps.finance.views.bank_account import BankAccountListView, BankAccountUpdateView, BankAccountCreateView
from apps.finance.views.payment_method import PaymentMethodListView, PaymentMethodCreateView, PaymentMethodUpdateView

app_name = "finance"

urlpatterns = [
    # Financial Groups
    path("financial-groups/", FinancialGroupListView.as_view(), name="financial_groups_list"),
    path("financial-groups/create/", FinancialGroupCreateView.as_view(), name="financial_groups_create"),
    path("financial-groups/<int:pk>/update/", FinancialGroupUpdateView.as_view(), name="financial_groups_update"),
    path("financial-groups/<int:pk>/delete/", FinancialGroupDeleteView.as_view(), name="financial_groups_delete"),
    # Payment Method
    path("payment-methods/", PaymentMethodListView.as_view(), name="payment_methods_list"),
    path("payment-methods/create/", PaymentMethodCreateView.as_view(), name="payment_methods_create"),
    path("payment-methods/<int:pk>/update/", PaymentMethodUpdateView.as_view(), name="payment_methods_update"),
    # Unified emission
    path("emissao/preview/", EmissionPreviewView.as_view(), name="emission_preview"),
    path("emissao/workorder/<int:workorder_pk>/item/<int:item_id>/edit/", EmissionWorkOrderItemUpdateView.as_view(), name="emission_workorder_item_edit"),
    path("emissao/workorder/<int:workorder_pk>/kit-item/<int:item_id>/<str:component_type>/<int:component_id>/edit/", EmissionWorkOrderKitComponentUpdateView.as_view(), name="emission_workorder_kit_component_edit"),
    path("emissao/", EmissionRequestCreateView.as_view(), name="emission_create"),
    # NFE
    path("nfe/", NfeRequestListView.as_view(), name="nfe_emit"),
    path("nfe/list/", NfeRequestListView.as_view(), name="nfe_list"),
    path("nfe/create/", NfeCreateRedirectView.as_view(), name="nfe_create"),
    path("nfe/<int:pk>/", NfeRequestDetailView.as_view(), name="nfe_detail"),
    path("nfe/<int:pk>/reconciliar/", NfeRequestReconcileView.as_view(), name="nfe_reconcile"),
    path("nfe/<int:pk>/documentos/<str:document>/", NfeDocumentDownloadView.as_view(), name="nfe_document_download"),
    path("nfe/<int:pk>/edit/", NfeRequestUpdateView.as_view(), name="nfe_update"),
    # Classe Imposto
    path("classe-imposto/", TaxClassListView.as_view(), name="tax_class_list"),
    path("classe-imposto/", TaxClassListView.as_view(), name="tax_class_manager"),
    path("classe-imposto/create/", TaxClassCreateView.as_view(), name="tax_class_create"),
    path("classe-imposto/<str:reference>/edit/", TaxClassUpdateView.as_view(), name="tax_class_update"),
    path("classe-imposto/presets/", TaxClassPresetListView.as_view(), name="tax_class_preset_list"),
    path("classe-imposto/presets/create/", TaxClassPresetCreateView.as_view(), name="tax_class_preset_create"),
    path("classe-imposto/presets/<int:pk>/edit/", TaxClassPresetUpdateView.as_view(), name="tax_class_preset_update"),
    # Bank Account
    path("bank-account/", BankAccountListView.as_view(), name="bank_account_list"),
    path("bank-account/create/", BankAccountCreateView.as_view(), name="bank_account_create"),
    path("bank-account/<int:pk>/update/", BankAccountUpdateView.as_view(), name="bank_account_update"),
    # NFS-e
    path("nfse/", NfseRequestListView.as_view(), name="nfse_list"),
    path("nfse/create/", NfseCreateRedirectView.as_view(), name="nfse_create"),
    path("nfse/<int:pk>/", NfseRequestDetailView.as_view(), name="nfse_detail"),
    path("nfse/<int:pk>/documentos/<str:document>/", NfseDocumentDownloadView.as_view(), name="nfse_document_download"),
    path("nfse/<int:pk>/edit/", NfseRequestUpdateView.as_view(), name="nfse_update"),
    # WebMania
    path("webmania/empresas/", WebmaniaCompanyListView.as_view(), name="webmania_company_list"),
    path("webmania/empresas/sync/", WebmaniaCompanySyncView.as_view(), name="webmania_company_sync"),
    path("webmania/empresas/<int:pk>/", WebmaniaCompanyDetailView.as_view(), name="webmania_company_detail"),
    path("webmania/empresas/<int:pk>/editar/", WebmaniaCompanyUpdateView.as_view(), name="webmania_company_update"),
    path("webmania/requisicoes/", RedirectView.as_view(pattern_name="workshops:emission_history", permanent=False), name="webmania_requests"),
    path("webmania/webhook/ping/", WebhookView.as_view(), name="webhook_ping"),
    path("webmania/webhook/", WebhookView.as_view(), name="webhook"),
]
