from django.urls import path
from django.views.generic import RedirectView

from apps.finance.views import (
    NfeRequestCreateView,
    NfeRequestListView,
    NfeRequestUpdateView,
    NfseRequestCreateView,
    NfseRequestListView,
    NfseRequestUpdateView,
    TaxClassCreateView,
    TaxClassListView,
    TaxClassUpdateView,
    WebhookView,
    WebmaniaCompanyDetailView,
    WebmaniaCompanyListView,
    WebmaniaCompanySyncView,
    WebmaniaCompanyUpdateView,
)
from apps.finance.views.payment_method import PaymentMethodListView, PaymentMethodCreateView, PaymentMethodUpdateView

app_name = "finance"

urlpatterns = [
    # Payment Method
    path("payment-methods/", PaymentMethodListView.as_view(), name="payment_methods_list"),
    path("payment-methods/create/", PaymentMethodCreateView.as_view(), name="payment_methods_create"),
    path("payment-methods/<int:pk>/update/", PaymentMethodUpdateView.as_view(), name="payment_methods_update"),

    # NFE
    path("nfe/", NfeRequestListView.as_view(), name="nfe_emit"),
    path("nfe/list/", NfeRequestListView.as_view(), name="nfe_list"),
    path("nfe/create/", NfeRequestCreateView.as_view(), name="nfe_create"),
    path("nfe/<int:pk>/edit/", NfeRequestUpdateView.as_view(), name="nfe_update"),

    # Classe Imposto
    path("classe-imposto/", TaxClassListView.as_view(), name="tax_class_list"),
    path("classe-imposto/", TaxClassListView.as_view(), name="tax_class_manager"),
    path("classe-imposto/create/", TaxClassCreateView.as_view(), name="tax_class_create"),
    path("classe-imposto/<str:reference>/edit/", TaxClassUpdateView.as_view(), name="tax_class_update"),

    # NFS-e
    path("nfse/", NfseRequestListView.as_view(), name="nfse_list"),
    path("nfse/create/", NfseRequestCreateView.as_view(), name="nfse_create"),
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
