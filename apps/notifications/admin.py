from django.contrib import admin
from apps.notifications.models import Notification, NotificationRecipient


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "sender", "criado_em")
    search_fields = ("title", "message", "sender__username", "sender__email")
    list_filter = ("criado_em",)


@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(admin.ModelAdmin):
    list_display = ("notification", "user", "workshop", "is_read", "read_at", "criado_em")
    list_filter = ("is_read", "workshop", "criado_em")
    search_fields = ("user__username", "user__email", "notification__title", "workshop__name")
