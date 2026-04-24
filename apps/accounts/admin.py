from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Account, FavoritePage, User


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner")
    search_fields = ("name",)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "account", "is_staff")


@admin.register(FavoritePage)
class FavoritePageAdmin(admin.ModelAdmin):
    list_display = ("user", "url", "position", "criado_em")
    list_filter = ("user",)
    search_fields = ("url", "user__username", "user__email")
