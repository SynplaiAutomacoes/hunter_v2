from django.contrib import admin

from apps.yard.models import YardColumn, YardHiddenStatus, YardPreference, YardStatusGroup


@admin.register(YardColumn)
class YardColumnAdmin(admin.ModelAdmin):
    list_display = ("title", "workshop", "target", "status", "date_base", "position")
    list_filter = ("target", "date_base")
    search_fields = ("title",)


@admin.register(YardHiddenStatus)
class YardHiddenStatusAdmin(admin.ModelAdmin):
    list_display = ("workshop", "target", "status")
    list_filter = ("target",)


@admin.register(YardStatusGroup)
class YardStatusGroupAdmin(admin.ModelAdmin):
    list_display = ("title", "workshop", "target")
    list_filter = ("target",)
    search_fields = ("title",)


@admin.register(YardPreference)
class YardPreferenceAdmin(admin.ModelAdmin):
    list_display = ("workshop", "hide_similar")
