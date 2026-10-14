"""Admin registrations for core app."""

from django.contrib import admin

from apps.core.infrastructure.models import MarketingLead


@admin.register(MarketingLead)
class MarketingLeadAdmin(admin.ModelAdmin):
    list_display = ("name", "workshop", "email", "whatsapp", "employees", "revenue", "criado_em")
    list_filter = ("employees", "revenue", "consent")
    search_fields = ("name", "workshop", "email", "whatsapp")
    readonly_fields = ("submission_id", "criado_em", "atualizado_em")
    ordering = ("-criado_em",)
