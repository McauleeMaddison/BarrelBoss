"""
Django settings for taptrack project.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from taptrack.database_config import build_database_settings, env_flag, trim_env

BASE_DIR = Path(__file__).resolve().parent.parent
RUNNING_TESTS = "test" in sys.argv
RUNNING_ON_RENDER = env_flag("RENDER", False) or bool(trim_env("RENDER_EXTERNAL_HOSTNAME"))
DEBUG = env_flag("DJANGO_DEBUG", default=not RUNNING_ON_RENDER)


def _parse_csv_env(name, default=""):
    return [
        item.strip()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    ]


def _unique_preserving_order(items):
    seen = set()
    ordered = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _host_is_local(host):
    normalized = (host or "").strip().lower()
    if not normalized:
        return True
    return normalized.split(":")[0] in {"localhost", "127.0.0.1", "::1", "[::1]"}


_secret_key = trim_env("DJANGO_SECRET_KEY")
if _secret_key:
    SECRET_KEY = _secret_key
elif DEBUG:
    SECRET_KEY = "barrelboss-local-dev-secret-key-change-before-production-1234567890"
else:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set when DEBUG is false."
    )

render_external_hostname = trim_env("RENDER_EXTERNAL_HOSTNAME")
default_allowed_hosts = "127.0.0.1,localhost" if DEBUG else ""
ALLOWED_HOSTS = _parse_csv_env("DJANGO_ALLOWED_HOSTS", default_allowed_hosts)
if render_external_hostname:
    ALLOWED_HOSTS.append(render_external_hostname)
ALLOWED_HOSTS = _unique_preserving_order(ALLOWED_HOSTS)

CSRF_TRUSTED_ORIGINS = _parse_csv_env("DJANGO_CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [
        f"https://{host}"
        for host in ALLOWED_HOSTS
        if not _host_is_local(host)
    ]
if DEBUG:
    CSRF_TRUSTED_ORIGINS.extend(
        [
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ]
    )
CSRF_TRUSTED_ORIGINS = _unique_preserving_order(CSRF_TRUSTED_ORIGINS)

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts.apps.AccountsConfig",
    "apps.audit.apps.AuditConfig",
    "apps.dashboard.apps.DashboardConfig",
    "apps.stock.apps.StockConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.suppliers.apps.SuppliersConfig",
    "apps.breakages.apps.BreakagesConfig",
    "apps.checklists.apps.ChecklistsConfig",
    "apps.shifts.apps.ShiftsConfig",
    "apps.sales.apps.SalesConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.ActiveVenueMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.SessionIdleTimeoutMiddleware",
    "apps.accounts.middleware.SecurityHeadersMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "taptrack.urls"

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
                "apps.accounts.context_processors.role_context",
            ],
        },
    },
]

WSGI_APPLICATION = "taptrack.wsgi.application"

DATABASE_SSL_REQUIRE = env_flag("DATABASE_SSL_REQUIRE", True)
DATABASE_CONNECT_TIMEOUT = int(os.getenv("DATABASE_CONNECT_TIMEOUT", "15"))
DATABASES, _ = build_database_settings(
    BASE_DIR,
    ssl_require=DATABASE_SSL_REQUIRE,
    connect_timeout=DATABASE_CONNECT_TIMEOUT,
)

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Europe/London")
USE_I18N = True
USE_TZ = True

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "barrelboss-default-cache",
    }
}

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

if RUNNING_TESTS:
    STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
else:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
CSRF_FAILURE_VIEW = "taptrack.views.csrf_failure"
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    (
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    ),
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "25"))
EMAIL_HOST_USER = trim_env("DJANGO_EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = trim_env("DJANGO_EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_flag("DJANGO_EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_flag("DJANGO_EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = int(os.getenv("DJANGO_EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = trim_env("DJANGO_DEFAULT_FROM_EMAIL") or (
    "BarrelBoss <no-reply@localhost>" if DEBUG else ""
)
SERVER_EMAIL = trim_env("DJANGO_SERVER_EMAIL") or DEFAULT_FROM_EMAIL or "root@localhost"
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "86400"))
POS_WEBHOOK_MAX_BODY_BYTES = int(os.getenv("POS_WEBHOOK_MAX_BODY_BYTES", "131072"))

LOGIN_THROTTLE_FAILURE_LIMIT = int(os.getenv("LOGIN_THROTTLE_FAILURE_LIMIT", "5"))
LOGIN_THROTTLE_WINDOW_SECONDS = int(os.getenv("LOGIN_THROTTLE_WINDOW_SECONDS", "900"))
LOGIN_THROTTLE_LOCKOUT_SECONDS = int(os.getenv("LOGIN_THROTTLE_LOCKOUT_SECONDS", "900"))
SESSION_IDLE_TIMEOUT_SECONDS = int(
    os.getenv(
        "SESSION_IDLE_TIMEOUT_SECONDS",
        "1800" if not DEBUG else "86400",
    )
)
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "43200"))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = env_flag(
    "SESSION_EXPIRE_AT_BROWSER_CLOSE",
    default=not DEBUG,
)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = os.getenv(
    "DJANGO_SECURE_REFERRER_POLICY",
    "strict-origin-when-cross-origin",
)
SECURE_CROSS_ORIGIN_OPENER_POLICY = os.getenv(
    "DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY",
    "same-origin",
)

WEB_PUSH_PUBLIC_KEY = os.getenv("WEB_PUSH_PUBLIC_KEY", "").strip()
WEB_PUSH_PRIVATE_KEY = os.getenv("WEB_PUSH_PRIVATE_KEY", "").strip()
WEB_PUSH_SUBJECT = os.getenv("WEB_PUSH_SUBJECT", "").strip()
ALLOW_DEMO_ACCOUNT_BOOTSTRAP = env_flag("ALLOW_DEMO_ACCOUNT_BOOTSTRAP", DEBUG)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_flag("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_flag(
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", True
    )
    SECURE_HSTS_PRELOAD = env_flag("DJANGO_SECURE_HSTS_PRELOAD", True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
