from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone

from .tenancy import resolve_active_membership

SESSION_ACTIVITY_KEY = "barrelboss_last_activity"


def _content_security_policy():
    directives = {
        "default-src": ["'self'"],
        "base-uri": ["'self'"],
        "connect-src": ["'self'"],
        "font-src": ["'self'", "https://fonts.gstatic.com", "data:"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
        "img-src": ["'self'", "data:"],
        "manifest-src": ["'self'"],
        "object-src": ["'none'"],
        "script-src": ["'self'"],
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
        "worker-src": ["'self'", "blob:"],
    }
    if not settings.DEBUG:
        directives["upgrade-insecure-requests"] = []

    return "; ".join(
        f"{directive} {' '.join(values)}".rstrip()
        for directive, values in directives.items()
    )


class ActiveVenueMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_membership = None
        request.active_venue = None
        request.active_organisation = None

        if getattr(request, "user", None) and request.user.is_authenticated:
            membership = resolve_active_membership(request)
            if membership:
                request.active_membership = membership
                request.active_venue = membership.venue
                request.active_organisation = membership.venue.organisation

        return self.get_response(request)


class SessionIdleTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timeout_seconds = int(getattr(settings, "SESSION_IDLE_TIMEOUT_SECONDS", 0) or 0)

        if (
            timeout_seconds > 0
            and getattr(request, "user", None)
            and request.user.is_authenticated
        ):
            now_ts = int(timezone.now().timestamp())
            last_activity_ts = int(request.session.get(SESSION_ACTIVITY_KEY, 0) or 0)

            if last_activity_ts and now_ts - last_activity_ts > timeout_seconds:
                logout(request)
                if hasattr(request, "_messages"):
                    messages.info(
                        request,
                        "Your session expired after inactivity. Please sign in again.",
                    )
                login_url = redirect("login")
                if request.method == "GET":
                    full_path = request.get_full_path()
                    next_param = f"?next={quote(full_path)}" if full_path else ""
                    login_url["Location"] = f"{login_url['Location']}{next_param}"
                return login_url

            request.session[SESSION_ACTIVITY_KEY] = now_ts

        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._content_security_policy_value = _content_security_policy()

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith("/admin/"):
            return response

        response.headers.setdefault(
            "Content-Security-Policy",
            self._content_security_policy_value,
        )
        response.headers.setdefault(
            "Permissions-Policy",
            (
                "accelerometer=(), autoplay=(), camera=(), display-capture=(), "
                "geolocation=(), gyroscope=(), magnetometer=(), microphone=(), "
                "payment=(), usb=()"
            ),
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        return response
