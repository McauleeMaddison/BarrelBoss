from django.conf import settings
from django.core.checks import Error, Tags, register


LOCAL_HOST_ALIASES = {"localhost", "127.0.0.1", "::1", "[::1]"}
INSECURE_EMAIL_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
}
SECRET_KEY_BLOCKLIST = {
    "replace-me",
    "change-me",
    "django-insecure-%8hbp6^3)1$hv+!-u6t2(1ng1ap$r17v#px+@@*x65bccsj(98",
}


def _is_local_host(host):
    normalized = (host or "").strip().lower()
    if not normalized:
        return True
    hostname = normalized.split(":")[0]
    return hostname in LOCAL_HOST_ALIASES


@register(Tags.security, deploy=True)
def check_production_hardening_settings(app_configs, **kwargs):
    errors = []

    if settings.DEBUG:
        return errors

    if getattr(settings, "ALLOW_DEMO_ACCOUNT_BOOTSTRAP", False):
        errors.append(
            Error(
                "Demo account bootstrap must be disabled when DEBUG is false.",
                hint="Set ALLOW_DEMO_ACCOUNT_BOOTSTRAP=false in production.",
                id="accounts.E201",
            )
        )

    secret_key = (getattr(settings, "SECRET_KEY", "") or "").strip()
    if (
        not secret_key
        or secret_key in SECRET_KEY_BLOCKLIST
        or secret_key.startswith("django-insecure-")
    ):
        errors.append(
            Error(
                "SECRET_KEY is not hardened for production use.",
                hint="Use a long random DJANGO_SECRET_KEY generated for production.",
                id="accounts.E202",
            )
        )

    allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
    if not allowed_hosts or not any(not _is_local_host(host) for host in allowed_hosts):
        errors.append(
            Error(
                "ALLOWED_HOSTS is not configured with a non-local production host.",
                hint="Set DJANGO_ALLOWED_HOSTS to your real production domain(s).",
                id="accounts.E203",
            )
        )

    trusted_origins = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
    if not trusted_origins or any(
        not origin.strip().lower().startswith("https://")
        for origin in trusted_origins
        if origin.strip()
    ):
        errors.append(
            Error(
                "CSRF_TRUSTED_ORIGINS must contain HTTPS production origin(s).",
                hint=(
                    "Set DJANGO_CSRF_TRUSTED_ORIGINS to comma-separated HTTPS "
                    "origins, e.g. https://app.example.com."
                ),
                id="accounts.E204",
            )
        )

    if not getattr(settings, "SESSION_COOKIE_SECURE", False):
        errors.append(
            Error(
                "SESSION_COOKIE_SECURE must be enabled when DEBUG is false.",
                hint="Set SESSION_COOKIE_SECURE=true in production.",
                id="accounts.E205",
            )
        )

    if not getattr(settings, "CSRF_COOKIE_SECURE", False):
        errors.append(
            Error(
                "CSRF_COOKIE_SECURE must be enabled when DEBUG is false.",
                hint="Set CSRF_COOKIE_SECURE=true in production.",
                id="accounts.E206",
            )
        )

    if not getattr(settings, "SECURE_SSL_REDIRECT", False):
        errors.append(
            Error(
                "SECURE_SSL_REDIRECT must be enabled when DEBUG is false.",
                hint="Set DJANGO_SECURE_SSL_REDIRECT=true in production.",
                id="accounts.E207",
            )
        )

    if int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0) <= 0:
        errors.append(
            Error(
                "SECURE_HSTS_SECONDS must be greater than zero in production.",
                hint="Set DJANGO_SECURE_HSTS_SECONDS to a positive value such as 31536000.",
                id="accounts.E208",
            )
        )

    email_backend = (getattr(settings, "EMAIL_BACKEND", "") or "").strip()
    if not email_backend or email_backend in INSECURE_EMAIL_BACKENDS:
        errors.append(
            Error(
                "EMAIL_BACKEND must point to a real outbound mail backend in production.",
                hint="Set DJANGO_EMAIL_BACKEND to your SMTP or transactional mail backend.",
                id="accounts.E209",
            )
        )

    default_from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip().lower()
    if (
        not default_from_email
        or "@localhost" in default_from_email
        or "example.com" in default_from_email
    ):
        errors.append(
            Error(
                "DEFAULT_FROM_EMAIL must be configured with a real sender address in production.",
                hint="Set DJANGO_DEFAULT_FROM_EMAIL to a monitored sender such as no-reply@yourdomain.com.",
                id="accounts.E210",
            )
        )

    return errors
