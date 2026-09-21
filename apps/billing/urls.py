from django.urls import path

from apps.billing.presentation.views import (
    BillingPortalView,
    CheckoutSessionView,
    CheckoutSuccessView,
    PlansView,
    SubscribeCompleteView,
    SubscribeStartView,
    SubscribeStatusView,
    SubscribeView,
    SubscriberListView,
    UpgradeRequiredView,
)
from apps.billing.presentation.webhooks import StripeWebhookView

app_name = "billing"

urlpatterns = [
    path("planos/", PlansView.as_view(), name="plans"),
    path("assinar/", SubscribeView.as_view(), name="subscribe"),
    path("assinar/iniciar/", SubscribeStartView.as_view(), name="subscribe_start"),
    path("assinar/status/<int:pending_id>/", SubscribeStatusView.as_view(), name="subscribe_status"),
    path("assinar/concluir/", SubscribeCompleteView.as_view(), name="subscribe_complete"),
    path("checkout/", CheckoutSessionView.as_view(), name="checkout"),
    path("checkout/sucesso/", CheckoutSuccessView.as_view(), name="checkout_success"),
    path("portal/", BillingPortalView.as_view(), name="portal"),
    path("upgrade/", UpgradeRequiredView.as_view(), name="upgrade_required"),
    path("assinantes/", SubscriberListView.as_view(), name="subscriber_list"),
    path("webhook/ping/", StripeWebhookView.as_view(), name="webhook_ping"),
    path("webhook/", StripeWebhookView.as_view(), name="webhook"),
]
