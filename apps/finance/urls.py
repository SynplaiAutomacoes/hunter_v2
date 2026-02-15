from django.urls import path

from apps.finance.views import WebhookView

app_name = "finance"

urlpatterns = [
    path("webmania/webhook/ping/", WebhookView.as_view(), name="webhook_ping"),
    path("webmania/webhook/", WebhookView.as_view(), name="webhook"),
]