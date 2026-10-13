from django.contrib import admin

from apps.support_chat.models import ChatBlockedUser, ChatDisabledWorkshop, ChatSession


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id", "member", "workshop", "is_active", "message_count", "last_interaction_at")
    list_filter = ("is_active", "workshop")
    search_fields = ("session_id",)
    readonly_fields = ("session_id",)


@admin.register(ChatBlockedUser)
class ChatBlockedUserAdmin(admin.ModelAdmin):
    list_display = ("user", "blocked_by", "criado_em")
    search_fields = ("user__username",)


@admin.register(ChatDisabledWorkshop)
class ChatDisabledWorkshopAdmin(admin.ModelAdmin):
    list_display = ("workshop", "disabled_by", "criado_em")
    search_fields = ("workshop__name",)
