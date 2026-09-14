from django.contrib import admin

from apps.billing.models import AccountSubscription, StripeWebhookEvent


@admin.register(AccountSubscription)
class AccountSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("account", "plan", "status", "stripe_customer_id", "current_period_end", "criado_em")
    list_filter = ("plan", "status")
    search_fields = ("account__name", "stripe_customer_id", "stripe_subscription_id")
    raw_id_fields = ("account",)


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed_at", "criado_em")
    list_filter = ("event_type",)
    search_fields = ("event_id", "event_type")
    readonly_fields = ("event_id", "event_type", "payload", "processed_at", "criado_em", "atualizado_em")
