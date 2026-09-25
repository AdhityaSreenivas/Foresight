"""
PSIF Platform — accounts app

Custom User model with role-based access control.

Roles:
  admin         — full access, including model retraining and user management
  safety_officer — upload/process datasets, view all incidents/predictions/reports,
                   run manual predictions
  analyst       — view incidents/predictions/reports, run manual predictions;
                  cannot upload datasets or retrain
  viewer        — read-only access to dashboard and reports
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Extended User model.
    All auth fields (username, email, password, is_staff, etc.) are inherited
    from AbstractUser.  We add a single `role` field that drives permission
    checks throughout the application.

    Role enforcement is done at the API layer via DRF permission classes —
    hiding a UI element is NOT sufficient on its own.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        SAFETY_OFFICER = "safety_officer", "Safety Officer"
        ANALYST = "analyst", "Analyst"
        VIEWER = "viewer", "Viewer"
        ADMIN_FLOW = "admin_flow", "Admin Flow"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER,
        help_text="Determines what the user can see and do in the platform.",
    )

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["username"]

    def __str__(self) -> str:
        return f"{self.username} ({self.get_role_display()})"

    # ── Convenience role-check properties ─────────────────────────────────────

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN

    @property
    def is_safety_officer(self) -> bool:
        return self.role == self.Role.SAFETY_OFFICER

    @property
    def is_analyst(self) -> bool:
        return self.role == self.Role.ANALYST

    @property
    def is_viewer(self) -> bool:
        return self.role == self.Role.VIEWER

    @property
    def is_admin_flow(self) -> bool:
        return self.role == self.Role.ADMIN_FLOW

    @property
    def can_upload(self) -> bool:
        """Can upload and process datasets."""
        return self.role in (self.Role.ADMIN, self.Role.SAFETY_OFFICER)

    @property
    def can_retrain(self) -> bool:
        """Can trigger model retraining."""
        return self.role == self.Role.ADMIN

    @property
    def can_predict(self) -> bool:
        """Can run manual single-incident predictions."""
        return self.role in (
            self.Role.ADMIN,
            self.Role.SAFETY_OFFICER,
            self.Role.ANALYST,
        )
