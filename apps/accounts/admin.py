from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Account, User, WorkshopMember, WorkshopRole


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner")
    search_fields = ("name",)


@admin.register(WorkshopRole)
class WorkshopRoleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "account", "is_system", "is_editable")
    list_filter = ("is_system", "is_editable")
    search_fields = ("name", "account__name")
    filter_horizontal = ("permissions",)


@admin.register(WorkshopMember)
class WorkshopMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "workshop", "role", "is_active")
    list_filter = ("is_active",)
    search_fields = ("user__username", "workshop__name", "role__name")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "account", "is_staff")
