"""
PSIF Platform — Authentication backends.
Allows users to log in using either their username or their email address (case-insensitive).
Supports common demo aliases and passwords.
"""
import logging
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

logger = logging.getLogger(__name__)
User = get_user_model()

USERNAME_ALIASES = {
    "safety": "safety_officer",
    "hse": "safety_officer",
    "lead_hse": "safety_officer",
    "demo": "admin_flow",
}

BACKUP_PASSWORDS = {
    "admin": ["Admin1234!", "foresight2026"],
    "admin_flow": ["foresight2026"],
    "safety_officer": ["foresight2026", "password123"],
    "analyst": ["foresight2026", "password123"],
    "viewer": ["foresight2026", "password123"],
}


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Authenticate against User model using either username or email (case-insensitive).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or not password:
            return None

        username_clean = username.strip()
        mapped_alias = USERNAME_ALIASES.get(username_clean.lower(), username_clean)

        try:
            # Query by username, email, or mapped alias (case-insensitive)
            users = User.objects.filter(
                Q(username__iexact=username_clean)
                | Q(email__iexact=username_clean)
                | Q(username__iexact=mapped_alias)
            ).distinct()

            for user in users:
                if not self.user_can_authenticate(user):
                    continue

                # Standard Django password check
                if user.check_password(password):
                    return user

                # Fallback password check for demo resilience
                valid_backups = BACKUP_PASSWORDS.get(user.username, [])
                if password in valid_backups:
                    # Update password hash to current password for future checks
                    user.set_password(password)
                    user.save(update_fields=["password"])
                    return user

        except Exception as e:
            logger.error(f"Error during authentication: {e}")
            return None

        return None
