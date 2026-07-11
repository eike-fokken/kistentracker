"""Django admin registrations for the dbtrials models."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from dbtrials.models import (
    Cookinggroup,
    ItemType,
    Packstreet,
    Rental,
    RentalAction,
    User,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the custom user model, exposing the application role."""

    list_display = ("username", "email", "role", "is_staff", "is_superuser")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")


@admin.register(Packstreet)
class PackstreetAdmin(admin.ModelAdmin):
    """Admin for packstreets."""

    list_display = ("name",)
    search_fields = ("name",)


@admin.register(ItemType)
class ItemTypeAdmin(admin.ModelAdmin):
    """Admin for the admin-managed item types."""

    list_display = ("label", "key")
    search_fields = ("label", "key")
    prepopulated_fields = {"key": ("label",)}


@admin.register(Cookinggroup)
class CookinggroupAdmin(admin.ModelAdmin):
    """Admin for rental groups."""

    list_display = ("internal_id", "name", "packstreet")
    list_filter = ("packstreet",)
    search_fields = ("name", "internal_id")


@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
    """Admin for current rental quantities."""

    list_display = ("group", "item_type", "quantity")
    list_filter = ("item_type",)
    search_fields = ("group__name", "group__internal_id")


@admin.register(RentalAction)
class RentalActionAdmin(admin.ModelAdmin):
    """Admin for the rental audit log."""

    list_display = ("timestamp", "action", "item_type", "quantity", "group", "user")
    list_filter = ("action", "item_type")
    search_fields = ("group__name", "group__internal_id", "user__username")
    readonly_fields = ("timestamp",)
