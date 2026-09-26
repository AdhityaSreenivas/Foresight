"""
PSIF Platform — Base Django Settings
All environment-specific overrides live in dev.py / prod.py.
Configuration is loaded from .env via django-environ.
"""

from pathlib import Path
import os
import sys
import environ

# Prevent OpenMP library clash between PyTorch and XGBoost on macOS
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
if sys.platform == "darwin":
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

# ── Path setup ────────────────────────────────────────────────────────────────
# BASE_DIR points to the project root (where manage.py lives)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Read the .env file at project root (silently ignored if absent in prod)
environ.Env.read_env(BASE_DIR / ".env", overwrite=True)

# ── Clean up and normalize environment variables ──────────────────────────────
# Strip surrounding quotes and pop empty strings so defaults take effect
# rather than throwing ValueError on type conversion.
for _k, _v in list(os.environ.items()):
    _stripped = _v.strip()
    if (_stripped.startswith('"') and _stripped.endswith('"')) or (_stripped.startswith("'") and _stripped.endswith("'")):
        _stripped = _stripped[1:-1].strip()
        os.environ[_k] = _stripped
    if _stripped == "":
        os.environ.pop(_k, None)

# ── Environment loading ───────────────────────────────────────────────────────
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "testserver"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DATABASE_URL=(str, ""),
    MAX_UPLOAD_SIZE_MB=(int, 250),
    BERT_BATCH_SIZE=(int, 32),
    PSIF_THRESHOLD=(float, 0.5),
    RISK_LOW_MAX=(float, 0.25),
    RISK_MEDIUM_MAX=(float, 0.50),
    RISK_HIGH_MAX=(float, 0.75),
)

# ── Core ──────────────────────────────────────────────────────────────────────
SECRET_KEY = env("SECRET_KEY", default="django-insecure-production-must-override-this-secret-key-properly")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
for host in [".vercel.app", ".now.sh", "localhost", "127.0.0.1", "testserver"]:
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)
if os.environ.get("VERCEL_URL") and os.environ["VERCEL_URL"] not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(os.environ["VERCEL_URL"])

CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
for origin in ["https://*.vercel.app", "https://*.now.sh", "http://localhost:8000", "http://127.0.0.1:8000"]:
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)
if os.environ.get("VERCEL_URL"):
    v_origin = f"https://{os.environ['VERCEL_URL']}"
    if v_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(v_origin)

# ── Application definition ────────────────────────────────────────────────────
INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    # Project apps (under apps/)
    "apps.accounts",
    "apps.datasets",
    "apps.incidents",
    "apps.predictions",
    "apps.dashboard",
    "apps.admin_flow",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ── Database — PostgreSQL 15 + psycopg 3 ─────────────────────────────────────
database_url = env("DATABASE_URL", default="").strip("\"' ")
if database_url:
    DATABASES = {
        "default": env.db_url_config(database_url)
    }
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
    DATABASES["default"].setdefault("OPTIONS", {})["cursor_factory"] = None
    if not DATABASES["default"].get("ENGINE"):
        DATABASES["default"]["ENGINE"] = "django.db.backends.postgresql"
else:
    DATABASES = {
        "default": {
            "ENGINE": env("DB_ENGINE", default="django.db.backends.postgresql"),
            "NAME": env("DB_NAME", default="psif_platform"),
            "USER": env("DB_USER", default="sas"),
            "PASSWORD": env("DB_PASSWORD", default=""),
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="5432"),
            "OPTIONS": {
                # psycopg 3 client-side cursor factory (improves streaming perf)
                "cursor_factory": None,
            },
            "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        }
    }

# ── Custom User model ─────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrUsernameModelBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ── Auth redirects ────────────────────────────────────────────────────────────
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# ── Password validation ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── Media files (uploaded datasets) ──────────────────────────────────────────
MEDIA_URL = "/media/"
if os.environ.get("VERCEL"):
    MEDIA_ROOT = Path("/tmp/media")
else:
    MEDIA_ROOT = BASE_DIR / env("MEDIA_ROOT", default="media")

try:
    os.makedirs(MEDIA_ROOT, exist_ok=True)
except Exception:
    pass

# Maximum upload size in bytes (default 250MB, minimum 250MB)
MAX_UPLOAD_SIZE_MB = max(250, env.int("MAX_UPLOAD_SIZE_MB", default=250))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ── File upload settings ──────────────────────────────────────────────────────
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_BYTES

# ── Default primary key ───────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# ── Celery ────────────────────────────────────────────────────────────────────
_default_redis_url = env("REDIS_URL", default="")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=_default_redis_url or "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=_default_redis_url or "redis://127.0.0.1:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Redis TLS configuration (e.g. for Upstash rediss:// endpoints)
if "rediss://" in CELERY_BROKER_URL:
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": None}
if "rediss://" in CELERY_RESULT_BACKEND:
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": None}

# Upstash / remote Redis keepalive and resilience options
CELERY_REDIS_SOCKET_KEEPALIVE = True
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_keepalive": True,
    "retry_on_timeout": True,
    "socket_timeout": 30.0,
    "socket_connect_timeout": 30.0,
    "health_check_interval": 25,
}
CELERY_REDIS_BACKEND_TRANSPORT_OPTIONS = {
    "socket_keepalive": True,
    "retry_on_timeout": True,
    "socket_timeout": 30.0,
    "socket_connect_timeout": 30.0,
    "health_check_interval": 25,
}

# Reliability & crash resilience
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# Use solo pool on macOS/Darwin to avoid unsafe fork() after PyTorch/XGBoost/OpenMP initialization
CELERY_WORKER_POOL = env("CELERY_WORKER_POOL", default="solo" if sys.platform == "darwin" else "prefork")
CELERY_WORKER_CONCURRENCY = env.int("CELERY_WORKER_CONCURRENCY", default=1 if sys.platform == "darwin" else 4)

DEV_SYNC_FALLBACK = env.bool("DEV_SYNC_FALLBACK", default=False)

# ── Cache Configuration (Redis) ──────────────────────────────────────────────
IS_TESTING = "test" in sys.argv or "pytest" in sys.modules or env.bool("TESTING", default=False)
redis_url = env("REDIS_URL", default="")
is_local_redis = (not redis_url) or ("127.0.0.1" in redis_url) or ("localhost" in redis_url)

if IS_TESTING or (os.environ.get("VERCEL") and is_local_redis):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "default-cache",
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": env("CACHE_BACKEND", default="django.core.cache.backends.redis.RedisCache"),
            "LOCATION": env("CACHE_LOCATION", default=env("REDIS_URL", default="redis://127.0.0.1:6379/2")),
            "TIMEOUT": 300,
        }
    }

# ── ML / NLP configuration ────────────────────────────────────────────────────
BERT_MODEL_NAME = env("BERT_MODEL_NAME", default="distilbert-base-uncased")
BERT_BATCH_SIZE = env("BERT_BATCH_SIZE")

# PSIF classification threshold (probability above which is_psif_predicted = True)
PSIF_THRESHOLD = env("PSIF_THRESHOLD")

# ── Risk level probability bands ──────────────────────────────────────────────
# Used consistently in: model_inference.py, serializers, frontend badge coloring
# low:      [0,      RISK_LOW_MAX)
# medium:   [RISK_LOW_MAX,    RISK_MEDIUM_MAX)
# high:     [RISK_MEDIUM_MAX, RISK_HIGH_MAX)
# critical: [RISK_HIGH_MAX,   1.0]
RISK_BANDS = {
    "LOW_MAX": env("RISK_LOW_MAX"),       # default 0.25
    "MEDIUM_MAX": env("RISK_MEDIUM_MAX"),  # default 0.50
    "HIGH_MAX": env("RISK_HIGH_MAX"),      # default 0.75
}

# ── ML Artifacts directory ────────────────────────────────────────────────────
ML_ARTIFACTS_DIR = BASE_DIR / env("ML_ARTIFACTS_DIR", default="ml_engine/artifacts")

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "apps.datasets": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "apps.incidents": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "apps.predictions": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "ml_engine": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
