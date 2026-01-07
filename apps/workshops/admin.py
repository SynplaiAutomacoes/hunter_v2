from django.contrib import admin

from apps.workshops.models import Workshop, WorkshopMember


@admin.register(Workshop)
class WorkshopAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "account", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "cnpj")


@admin.register(WorkshopMember)
class WorkshopMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "workshop", "role", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__username", "workshop__name", "role__name")
