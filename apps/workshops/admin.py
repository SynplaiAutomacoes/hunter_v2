from django.contrib import admin

from apps.workshops.models.workshops import Workshop


@admin.register(Workshop)
class WorkshopAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "account", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "cnpj")
