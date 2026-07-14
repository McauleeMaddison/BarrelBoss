from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

POSTGRES_ENV_KEYS = (
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
)

FALLBACK_DATABASE_ENV_KEYS = (
    "DATABASE_FALLBACK_URL",
    "RENDER_EXTERNAL_DATABASE_URL",
)


@dataclass(frozen=True)
class DatabaseUrlSelection:
    url: str
    source: str
    reason: str
    hostname: str


def env_flag(name, default=False, environ=None):
    value = (environ or os.environ).get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def trim_env(name, environ=None):
    return ((environ or os.environ).get(name) or "").strip()


def url_has_scheme(url):
    return "://" in url


def extract_hostname(database_url):
    if not database_url:
        return ""
    return urlparse(database_url).hostname or ""


def is_render_private_postgres_hostname(hostname):
    return hostname.startswith("dpg-") and "." not in hostname


def postgres_config_present(environ=None):
    return all(trim_env(env_key, environ) for env_key in POSTGRES_ENV_KEYS)


def get_fallback_database_url(environ=None):
    for env_key in FALLBACK_DATABASE_ENV_KEYS:
        env_value = trim_env(env_key, environ)
        if env_value:
            return env_value, env_key
    return "", ""


def select_database_url(environ=None):
    primary_url = trim_env("DATABASE_URL", environ)
    fallback_url, fallback_source = get_fallback_database_url(environ)
    primary_hostname = extract_hostname(primary_url)

    if primary_url and fallback_url:
        if not url_has_scheme(primary_url):
            return DatabaseUrlSelection(
                url=fallback_url,
                source=fallback_source,
                reason="invalid_primary_database_url",
                hostname=extract_hostname(fallback_url),
            )
        if is_render_private_postgres_hostname(primary_hostname):
            return DatabaseUrlSelection(
                url=fallback_url,
                source=fallback_source,
                reason="render_private_hostname",
                hostname=extract_hostname(fallback_url),
            )

    if primary_url:
        reason = "primary_database_url"
        if is_render_private_postgres_hostname(primary_hostname):
            reason = "render_private_hostname_without_fallback"
        return DatabaseUrlSelection(
            url=primary_url,
            source="DATABASE_URL",
            reason=reason,
            hostname=primary_hostname,
        )

    if fallback_url:
        return DatabaseUrlSelection(
            url=fallback_url,
            source=fallback_source,
            reason="fallback_database_url",
            hostname=extract_hostname(fallback_url),
        )

    return None


def parse_database_url(
    database_url,
    *,
    source="DATABASE_URL",
    conn_max_age=600,
    ssl_require=True,
):
    try:
        return dj_database_url.parse(
            database_url,
            conn_max_age=conn_max_age,
            ssl_require=ssl_require,
        )
    except ValueError as exc:
        scheme = database_url.split("://", 1)[0] if "://" in database_url else "<none>"
        raise ImproperlyConfigured(
            f"Invalid {source} environment variable. "
            f"Detected scheme: {scheme}. "
            "Expected a valid URL such as postgresql://USER:PASSWORD@HOST:5432/DBNAME."
        ) from exc


def build_database_settings(
    base_dir: Path,
    *,
    environ=None,
    conn_max_age=600,
    ssl_require=True,
    connect_timeout=15,
):
    selection = select_database_url(environ)

    if selection:
        default_database = parse_database_url(
            selection.url,
            source=selection.source,
            conn_max_age=conn_max_age,
            ssl_require=ssl_require,
        )
    elif postgres_config_present(environ):
        default_database = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": trim_env("POSTGRES_DB", environ),
            "USER": trim_env("POSTGRES_USER", environ),
            "PASSWORD": trim_env("POSTGRES_PASSWORD", environ),
            "HOST": trim_env("POSTGRES_HOST", environ),
            "PORT": trim_env("POSTGRES_PORT", environ),
        }
    else:
        default_database = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": base_dir / "db.sqlite3",
        }

    if default_database.get("ENGINE") == "django.db.backends.postgresql":
        default_options = default_database.setdefault("OPTIONS", {})
        default_options.setdefault("connect_timeout", connect_timeout)

    return {"default": default_database}, selection


def resolve_hostname(hostname):
    if not hostname:
        return True, ""

    try:
        socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        return False, str(exc)

    return True, ""
