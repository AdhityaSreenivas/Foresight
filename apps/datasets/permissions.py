"""
PSIF Platform — DRF Permission Classes

Provides role-based permission enforcement for API endpoints.
Each class maps to a specific capability defined in accounts.User.

IMPORTANT: Role enforcement is done HERE (at the API layer), not solely by
hiding UI elements.  Every state-changing endpoint has an explicit permission
class.
"""
from rest_framework.permissions import BasePermission


class CanUploadDataset(BasePermission):
    """
    Only admins and safety officers may upload and configure datasets.
    """
    message = "You must be an Admin or Safety Officer to upload datasets."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "can_upload", False)
        )


class CanViewDataset(BasePermission):
    """
    All authenticated users may list and view dataset status.
    """
    message = "You must be logged in to view datasets."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class CanRunPrediction(BasePermission):
    """
    Admins, safety officers, and analysts may run manual predictions.
    Viewers may not.
    """
    message = "You must be an Admin, Safety Officer, or Analyst to run predictions."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "can_predict", False)
        )


class IsAdminRole(BasePermission):
    """
    Only admins may access this endpoint (e.g., model retraining).
    Note: 'admin' here means role=admin, NOT Django is_staff/is_superuser.
    """
    message = "You must have the Admin role to perform this action."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_admin_role", False)
        )


class CanReviewIncident(BasePermission):
    """
    Only admins, safety officers, and analysts may submit human PSIF review
    decisions (writing is_psif_human_label as ground truth).

    Viewers may read incident data but must NOT be able to write training
    ground truth, as this would pollute the label dataset.

    Rationale: this maps to the same roles as CanRunPrediction because the
    same safety professionals who run predictions are also qualified to
    provide ground-truth PSIF classifications.
    """
    message = (
        "You must be an Admin, Safety Officer, or Analyst to submit "
        "a human PSIF review decision."
    )

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "can_predict", False)
        )
