from django.contrib import admin

from apps.terms.models import BudgetTermSigning, WorkOrderTermSigning, WorkshopTermTemplate


@admin.register(WorkshopTermTemplate)
class WorkshopTermTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "workshop", "template_type", "is_default", "is_active")
    list_filter = ("template_type", "is_active", "is_default")
    search_fields = ("name", "document_title")


@admin.register(BudgetTermSigning)
class BudgetTermSigningAdmin(admin.ModelAdmin):
    list_display = ("budget", "term_template", "signature_request_status", "signature_sent_at")
    list_filter = ("signature_request_status",)


@admin.register(WorkOrderTermSigning)
class WorkOrderTermSigningAdmin(admin.ModelAdmin):
    list_display = ("workorder", "term_template", "signature_request_status", "signature_sent_at")
    list_filter = ("signature_request_status",)
