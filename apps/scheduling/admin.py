from django.contrib import admin

from apps.scheduling.models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "customer", "vehicle", "starts_at", "ends_at", "status")
    list_filter = ("status", "workshop")
    search_fields = ("title", "customer__name", "vehicle__plate")
