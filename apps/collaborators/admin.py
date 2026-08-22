from django.contrib import admin

from apps.collaborators.models import WorkshopCollaborator, WorkshopMember


@admin.register(WorkshopMember)
class WorkshopMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "workshop", "role", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__username", "workshop__name", "role__name")


@admin.register(WorkshopCollaborator)
class WorkshopCollaboratorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "cpf", "workshop", "position", "is_active", "system_access")
    list_filter = ("is_active", "system_access", "collaborator_type", "receives_commission")
    search_fields = ("name", "cpf", "rg", "email", "position", "workshop__name")
    raw_id_fields = ("transport_budget_plan",)
