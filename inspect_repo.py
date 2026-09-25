import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from django.apps import apps
from django.urls import get_resolver

print("=== MODELS ===")
for app in apps.get_app_configs():
    for model in app.get_models():
        print(f"\nModel: {model.__name__} (App: {app.name})")
        for field in model._meta.fields:
            print(f" - {field.name}: {type(field).__name__}")

print("\n=== URLS ===")
def get_urls(url_patterns, prefix=''):
    for pattern in url_patterns:
        if hasattr(pattern, 'url_patterns'):
            get_urls(pattern.url_patterns, prefix + str(pattern.pattern))
        else:
            print(prefix + str(pattern.pattern))

get_urls(get_resolver().url_patterns)
