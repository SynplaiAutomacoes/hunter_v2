from django.urls import path

from apps.billing.presentation.views import (
    BillingPortalView,
    CheckoutSessionView,
    CheckoutSuccessView,
    OwnerSubscriptionCancelView,
    PlansView,
    SubscribeCompleteView,
    SubscribeConfirmSetupView,
    SubscribeSendCodeView,
    SubscribeStartView,
    SubscribeStatusView,
    SubscribeValidateCouponView,
    SubscribeVerifyCodeView,
    SubscribeView,
    SubscriberCancelView,
    SubscriberListView,
    UpgradeRequiredView,
)
from apps.billing.presentation.webhooks import StripeWebhookView

app_name = "billing"

urlpatterns = [
    path("planos/", PlansView.as_view(), name="plans"),
    path("assinar/", SubscribeView.as_view(), name="subscribe"),
    path("assinar/enviar-codigo/", SubscribeSendCodeView.as_view(), name="subscribe_send_code"),
    path("assinar/verificar-codigo/", SubscribeVerifyCodeView.as_view(), name="subscribe_verify_code"),
    path("assinar/validar-cupom/", SubscribeValidateCouponView.as_view(), name="subscribe_validate_coupon"),
    path("assinar/iniciar/", SubscribeStartView.as_view(), name="subscribe_start"),
    path("assinar/confirmar-setup/", SubscribeConfirmSetupView.as_view(), name="subscribe_confirm_setup"),
    path("assinar/status/<int:pending_id>/", SubscribeStatusView.as_view(), name="subscribe_status"),
    path("assinar/concluir/", SubscribeCompleteView.as_view(), name="subscribe_complete"),
    path("checkout/", CheckoutSessionView.as_view(), name="checkout"),
    path("checkout/sucesso/", CheckoutSuccessView.as_view(), name="checkout_success"),
    path("portal/", BillingPortalView.as_view(), name="portal"),
    path("assinatura/cancelar/", OwnerSubscriptionCancelView.as_view(), name="subscription_cancel"),
    path("upgrade/", UpgradeRequiredView.as_view(), name="upgrade_required"),
    path("assinantes/", SubscriberListView.as_view(), name="subscriber_list"),
    path("assinantes/<int:pk>/cancelar/", SubscriberCancelView.as_view(), name="subscriber_cancel"),
    path("webhook/ping/", StripeWebhookView.as_view(), name="webhook_ping"),
    path("webhook/", StripeWebhookView.as_view(), name="webhook"),
]
