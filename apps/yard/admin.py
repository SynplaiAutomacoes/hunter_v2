from django.contrib import admin

from apps.yard.models import YardColumn


@admin.register(YardColumn)
class YardColumnAdmin(admin.ModelAdmin):
    list_display = ("title", "workshop", "target", "status", "date_base", "position", "is_active")
    list_filter = ("target", "date_base", "is_active")
    search_fields = ("title",)
