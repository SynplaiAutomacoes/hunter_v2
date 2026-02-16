from django.urls import path

from apps.finance.views import NfePlaceholderView, NfseRequestCreateView, NfseRequestListView, NfseRequestUpdateView, WebhookView

app_name = "finance"

urlpatterns = [
    path("nfe/", NfePlaceholderView.as_view(), name="nfe_emit"),
    path("nfse/", NfseRequestListView.as_view(), name="nfse_list"),
    path("nfse/create/", NfseRequestCreateView.as_view(), name="nfse_create"),
    path("nfse/<int:pk>/edit/", NfseRequestUpdateView.as_view(), name="nfse_update"),
    path("webmania/webhook/ping/", WebhookView.as_view(), name="webhook_ping"),
    path("webmania/webhook/", WebhookView.as_view(), name="webhook"),
]
