from django.contrib import admin

from apps.tickets.models import Ticket, TicketAttachment, TicketMessage, TicketStatusHistory


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "workshop", "created_by", "assignee", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "problem")
    raw_id_fields = ("workshop", "created_by", "assignee")


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "original_name", "source", "size_bytes", "created_at")
    raw_id_fields = ("ticket", "uploaded_by")


@admin.register(TicketMessage)
class TicketMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "author", "created_at")
    raw_id_fields = ("ticket", "author")


@admin.register(TicketStatusHistory)
class TicketStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "ticket", "from_status", "to_status", "actor", "created_at")
    raw_id_fields = ("ticket", "actor")
