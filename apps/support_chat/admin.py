from django.contrib import admin

from apps.support_chat.models import ChatSession


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id", "member", "workshop", "is_active", "message_count", "last_interaction_at")
    list_filter = ("is_active", "workshop")
    search_fields = ("session_id",)
    readonly_fields = ("session_id",)
