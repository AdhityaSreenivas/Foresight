"""
PSIF Platform — Admin Flow Access Control & Authorization.

Ensures that only authorized Admin Flow users can access /admin-flow/ routes and APIs.
Normal users are denied access with HTTP 403 Forbidden.
"""
from functools import wraps
from django.contrib.auth.mixins import AccessMixin
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from rest_framework.permissions import BasePermission
from .services import is_admin_flow_user


def admin_flow_required(view_func):
    """
    Decorator for views that checks that the user is logged in and is an Admin Flow user.
    If not logged in, redirects to login.
    If logged in but not an Admin Flow user, returns HTTP 403 Forbidden.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            login_url = reverse("accounts:login")
            return HttpResponseRedirect(f"{login_url}?next={request.path}")
        if not is_admin_flow_user(request.user):
            return HttpResponseForbidden(
                "Access Denied: The Admin Flow workspace is restricted to authorized demonstration evaluators."
            )
        return view_func(request, *args, **kwargs)
    return _wrapped_view


class AdminFlowRequiredMixin(AccessMixin):
    """
    CBV mixin that verifies the current user is authenticated and has Admin Flow access.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not is_admin_flow_user(request.user):
            return HttpResponseForbidden(
                "Access Denied: The Admin Flow workspace is restricted to authorized demonstration evaluators."
            )
        return super().dispatch(request, *args, **kwargs)


class IsAdminFlowUser(BasePermission):
    """
    DRF permission class restricting API endpoints to Admin Flow users.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and is_admin_flow_user(request.user))
