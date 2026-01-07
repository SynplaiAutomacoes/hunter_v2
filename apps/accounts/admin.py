from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Account, User


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner")
    search_fields = ("name",)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "account", "is_staff")
