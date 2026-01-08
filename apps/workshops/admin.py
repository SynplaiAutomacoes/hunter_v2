from django.contrib import admin

from apps.workshops.models import Workshop, WorkshopEmployee, WorkshopMember


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


@admin.register(WorkshopEmployee)
class WorkshopEmployeeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "cpf", "workshop", "position", "is_active", "system_access")
    list_filter = ("is_active", "system_access", "employee_type", "receives_commission")
    search_fields = ("name", "cpf", "rg", "email", "position", "workshop__name")
