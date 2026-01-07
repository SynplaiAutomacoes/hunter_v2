from django.contrib import admin

from apps.iam.models import WorkshopRole


@admin.register(WorkshopRole)
class WorkshopRoleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "account", "is_system", "is_editable")
    list_filter = ("is_system", "is_editable")
    search_fields = ("name", "account__name")
    filter_horizontal = ("permissions",)
