import os
import warnings
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(REPO_ROOT / ".env")

# WhiteNoise warns when STATIC_ROOT does not exist yet (before collectstatic).
warnings.filterwarnings("ignore", message="No directory at")


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def env_bool(name: str, default: bool = False) -> bool:
    value = env_str(name)
    return value.lower() in {"1", "true", "yes", "on"} if value else default


def env_int(name: str, default: int) -> int:
    value = env_str(name)
    return int(value) if value else default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env_str(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env_str("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_DEBUG is off")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.api",
    "apps.bot",
]

# XFrameOptionsMiddleware is intentionally absent: the MAX web client may embed the mini-app in a frame.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.FrameAncestorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

FRAME_ANCESTORS = env_str("FRAME_ANCESTORS", "https://max.ru https://*.max.ru")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

if env_str("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env_str("POSTGRES_DB", "shiftcontrol"),
            "USER": env_str("POSTGRES_USER", "shiftcontrol"),
            "PASSWORD": env_str("POSTGRES_PASSWORD", "shiftcontrol"),
            "HOST": env_str("POSTGRES_HOST"),
            "PORT": env_str("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

LANGUAGE_CODE = "ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST

MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.auth.MaxInitDataAuthentication",
        "apps.api.auth.ReviewTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

BOT_TOKEN = env_str("BOT_TOKEN")
BOT_USERNAME = env_str("BOT_USERNAME")
MAX_API_BASE = env_str("MAX_API_BASE", "https://platform-api2.max.ru")
_ca_bundle = Path(env_str("MAX_CA_BUNDLE", "certs/Russian_Trusted_Root_CA.cer"))
MAX_CA_BUNDLE = _ca_bundle if _ca_bundle.is_absolute() else REPO_ROOT / _ca_bundle
PUBLIC_BASE_URL = env_str("PUBLIC_BASE_URL")

INIT_DATA_MAX_AGE_SECONDS = env_int("INIT_DATA_MAX_AGE_SECONDS", 86400)
# Автоматическая проверка хакатона (DATA-API.yaml): запросы с этим токеном идут от имени
# тестового владельца. Пусто — вход по токену выключен.
REVIEW_API_TOKEN = env_str("REVIEW_API_TOKEN")
REVIEW_OWNER_MAX_ID = env_int("REVIEW_OWNER_MAX_ID", 900000001)
# Напоминания отсчитываются от срока задачи: плановое время плюс её допуск.
REMINDER_FIRST_MINUTES_BEFORE = env_int("REMINDER_FIRST_MINUTES_BEFORE", 15)
REMINDER_FINAL_MINUTES_BEFORE = env_int("REMINDER_FINAL_MINUTES_BEFORE", 5)
CLAIM_ESCALATION_MINUTES_BEFORE = env_int("CLAIM_ESCALATION_MINUTES_BEFORE", 15)
PHOTO_WAIT_MINUTES = env_int("PHOTO_WAIT_MINUTES", 10)
SHIFT_BOUNDARY_TOLERANCE_MINUTES = env_int("SHIFT_BOUNDARY_TOLERANCE_MINUTES", 5)
SCHEDULER_INTERVAL_SECONDS = env_int("SCHEDULER_INTERVAL_SECONDS", 30)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env_str("LOG_LEVEL", "INFO")},
}
