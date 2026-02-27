from django.urls import path
from django.views.generic import RedirectView

from apps.finance.views import (
    NfePlaceholderView,
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

app_name = "finance"

urlpatterns = [
    path("nfe/", NfePlaceholderView.as_view(), name="nfe_emit"),
    path("classe-imposto/", TaxClassListView.as_view(), name="tax_class_list"),
    path("classe-imposto/", TaxClassListView.as_view(), name="tax_class_manager"),
    path("classe-imposto/create/", TaxClassCreateView.as_view(), name="tax_class_create"),
    path("classe-imposto/<str:reference>/edit/", TaxClassUpdateView.as_view(), name="tax_class_update"),
    path("nfse/", NfseRequestListView.as_view(), name="nfse_list"),
    path("nfse/create/", NfseRequestCreateView.as_view(), name="nfse_create"),
    path("nfse/<int:pk>/edit/", NfseRequestUpdateView.as_view(), name="nfse_update"),
    path("webmania/empresas/", WebmaniaCompanyListView.as_view(), name="webmania_company_list"),
    path("webmania/empresas/sync/", WebmaniaCompanySyncView.as_view(), name="webmania_company_sync"),
    path("webmania/empresas/<int:pk>/", WebmaniaCompanyDetailView.as_view(), name="webmania_company_detail"),
    path("webmania/empresas/<int:pk>/editar/", WebmaniaCompanyUpdateView.as_view(), name="webmania_company_update"),
    path("webmania/requisicoes/", RedirectView.as_view(pattern_name="workshops:emission_history", permanent=False), name="webmania_requests"),
    path("webmania/webhook/ping/", WebhookView.as_view(), name="webhook_ping"),
    path("webmania/webhook/", WebhookView.as_view(), name="webhook"),
]
