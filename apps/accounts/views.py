"""
PSIF Platform — Accounts views
"""

from django.contrib.auth.views import LoginView as DjangoLoginView
from django.urls import reverse_lazy
from django.views.generic import CreateView
from apps.dashboard.imagery import get_industrial_image


class LoginView(DjangoLoginView):
    template_name = "accounts/login.html"

    def get_success_url(self):
        user = self.request.user
        if user.is_authenticated and getattr(user, "is_admin_flow", False):
            return reverse_lazy("admin_flow:dashboard")
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hero_image'] = get_industrial_image(query='industrial safety', orientation='portrait')
        return context


from .forms import CustomUserCreationForm

class RegisterView(CreateView):
    """Simple registration view using Django's built-in UserCreationForm."""
    form_class = CustomUserCreationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hero_image'] = get_industrial_image(query='industrial safety worker', orientation='portrait')
        return context
