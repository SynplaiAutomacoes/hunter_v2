from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Columns in the list view
    list_display = ("username", "first_name", "role", "cpf", "is_active")
    list_filter = ("role", "workshops", "is_active")

    # Field layout when editing a user
    fieldsets = UserAdmin.fieldsets + (("Professional Information", {"fields": ("cpf", "role", "workshops")}),)

    # Field layout when creating a user
    add_fieldsets = UserAdmin.add_fieldsets + (("Professional Information", {"fields": ("cpf", "role", "workshops")}),)