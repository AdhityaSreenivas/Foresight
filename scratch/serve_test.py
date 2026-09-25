import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()
from django.core.management import call_command
call_command("runserver", "127.0.0.1:8000")
