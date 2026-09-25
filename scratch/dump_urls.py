import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.urls import get_resolver
from rest_framework.views import APIView

def get_urls():
    urlconf = get_resolver()
    all_urls = list(urlconf.url_patterns)
    
    def list_urls(lis, acc=None):
        if acc is None:
            acc = []
        if not lis:
            return
        l = lis[0]
        if hasattr(l, 'url_patterns'):
            yield from list_urls(l.url_patterns, acc + [str(l.pattern)])
        else:
            yield ''.join(acc) + str(l.pattern), l.callback
        yield from list_urls(lis[1:], acc)

    for url, view in list_urls(all_urls):
        view_name = f"{view.__module__}.{view.__name__}" if hasattr(view, '__name__') else str(view)
        perms = []
        if hasattr(view, 'view_class'):
            if hasattr(view.view_class, 'permission_classes'):
                perms = [p.__name__ for p in getattr(view.view_class, 'permission_classes', [])]
        print(f"URL: {url} | View: {view_name} | Perms: {perms}")

if __name__ == '__main__':
    get_urls()
