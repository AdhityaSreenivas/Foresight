# config/__init__.py
import os

# Prevent OpenMP library clash between PyTorch and XGBoost on macOS
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Pre-import xgboost to safely initialize native dylibs before torch/OpenMP on macOS
try:
    import xgboost  # noqa: F401
except ImportError:
    pass

# Make Celery app available when Django starts, so shared_task works.
from .celery import app as celery_app

# Python 3.14 compatibility patch for django.template.context.BaseContext.__copy__
try:
    from django.template.context import BaseContext
    def _base_context_copy(self):
        duplicate = object.__new__(self.__class__)
        duplicate.dicts = self.dicts[:]
        return duplicate
    BaseContext.__copy__ = _base_context_copy
except Exception:
    pass

__all__ = ("celery_app",)
