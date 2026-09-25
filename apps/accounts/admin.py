from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Custom admin for the extended User model."""

    # Add 'role' to the fieldsets
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("PSIF Platform Role", {"fields": ("role",)}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("PSIF Platform Role", {"fields": ("role",)}),
    )

    list_display = ["username", "email", "first_name", "last_name", "role", "is_staff"]
    list_filter = ["role", "is_staff", "is_superuser", "is_active"]
    search_fields = ["username", "email", "first_name", "last_name"]
