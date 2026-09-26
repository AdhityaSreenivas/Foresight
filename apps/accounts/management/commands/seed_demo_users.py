"""
Management command to seed or update demo users for Foresight PSIF Platform.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

DEMO_USERS = [
    {
        "username": "admin",
        "email": "admin@foresight.app",
        "password": "foresight2026",
        "role": User.Role.ADMIN,
        "is_staff": True,
        "is_superuser": True,
        "first_name": "System",
        "last_name": "Administrator",
    },
    {
        "username": "admin_flow",
        "email": "admin_flow@foresight.app",
        "password": "foresight2026",
        "role": User.Role.ADMIN_FLOW,
        "is_staff": True,
        "is_superuser": False,
        "first_name": "Demo",
        "last_name": "Evaluator",
    },
    {
        "username": "safety_officer",
        "email": "safety@foresight.app",
        "password": "foresight2026",
        "role": User.Role.SAFETY_OFFICER,
        "is_staff": False,
        "is_superuser": False,
        "first_name": "HSE",
        "last_name": "Officer",
    },
    {
        "username": "analyst",
        "email": "analyst@foresight.app",
        "password": "foresight2026",
        "role": User.Role.ANALYST,
        "is_staff": False,
        "is_superuser": False,
        "first_name": "Safety",
        "last_name": "Analyst",
    },
    {
        "username": "viewer",
        "email": "viewer@foresight.app",
        "password": "foresight2026",
        "role": User.Role.VIEWER,
        "is_staff": False,
        "is_superuser": False,
        "first_name": "Safety",
        "last_name": "Viewer",
    },
]


class Command(BaseCommand):
    help = "Seed or reset demo users for the Foresight platform"

    def handle(self, *args, **options):
        for user_data in DEMO_USERS:
            username = user_data["username"]
            email = user_data["email"]
            password = user_data["password"]
            role = user_data["role"]
            is_staff = user_data["is_staff"]
            is_superuser = user_data["is_superuser"]
            first_name = user_data.get("first_name", "")
            last_name = user_data.get("last_name", "")

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "role": role,
                    "is_staff": is_staff,
                    "is_superuser": is_superuser,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )

            # Ensure fields, role, and password are up to date
            user.email = email
            user.role = role
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.set_password(password)
            user.save()

            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} user '{username}' (email: {email}, role: {role})"))
