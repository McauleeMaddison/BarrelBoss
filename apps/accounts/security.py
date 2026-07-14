from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


@dataclass(frozen=True)
class LoginThrottleStatus:
    locked: bool
    retry_after_seconds: int = 0


def _now_ts() -> int:
    return int(timezone.now().timestamp())


def _normalize_username(username: str) -> str:
    normalized = (username or "").strip().lower()
    return normalized or "<blank>"


def _request_ip(request) -> str:
    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    if forwarded_for:
        return forwarded_for
    return (request.META.get("REMOTE_ADDR") or "unknown").strip() or "unknown"


def _throttle_settings():
    return {
        "limit": max(int(getattr(settings, "LOGIN_THROTTLE_FAILURE_LIMIT", 5) or 0), 1),
        "window_seconds": max(
            int(getattr(settings, "LOGIN_THROTTLE_WINDOW_SECONDS", 900) or 0),
            1,
        ),
        "lockout_seconds": max(
            int(getattr(settings, "LOGIN_THROTTLE_LOCKOUT_SECONDS", 900) or 0),
            1,
        ),
    }


def _cache_key(*parts: str) -> str:
    return "barrelboss:login-throttle:" + ":".join(parts)


def _read_state(key: str, *, now_ts: int, window_seconds: int) -> dict:
    state = cache.get(key) or {}
    first_failure_ts = int(state.get("first_failure_ts", 0) or 0)
    locked_until_ts = int(state.get("locked_until_ts", 0) or 0)
    failure_count = int(state.get("failure_count", 0) or 0)

    if locked_until_ts and locked_until_ts <= now_ts:
        return {}

    if first_failure_ts and now_ts - first_failure_ts >= window_seconds:
        return {}

    return {
        "first_failure_ts": first_failure_ts,
        "locked_until_ts": locked_until_ts,
        "failure_count": failure_count,
    }


def _write_state(key: str, state: dict, *, window_seconds: int, lockout_seconds: int) -> None:
    timeout = max(window_seconds, lockout_seconds) + 60
    cache.set(key, state, timeout)


def _candidate_keys(request, username: str) -> tuple[str, str]:
    ip_address = _request_ip(request)
    normalized_username = _normalize_username(username)
    return (
        _cache_key("ip", ip_address),
        _cache_key("ip-user", ip_address, normalized_username),
    )


def get_login_throttle_status(request, username: str) -> LoginThrottleStatus:
    config = _throttle_settings()
    now_ts = _now_ts()
    retry_after_seconds = 0

    for key in _candidate_keys(request, username):
        state = _read_state(key, now_ts=now_ts, window_seconds=config["window_seconds"])
        locked_until_ts = int(state.get("locked_until_ts", 0) or 0)
        if locked_until_ts > now_ts:
            retry_after_seconds = max(retry_after_seconds, locked_until_ts - now_ts)

    return LoginThrottleStatus(
        locked=retry_after_seconds > 0,
        retry_after_seconds=retry_after_seconds,
    )


def record_login_failure(request, username: str) -> LoginThrottleStatus:
    config = _throttle_settings()
    now_ts = _now_ts()

    for key in _candidate_keys(request, username):
        state = _read_state(key, now_ts=now_ts, window_seconds=config["window_seconds"])
        locked_until_ts = int(state.get("locked_until_ts", 0) or 0)
        if locked_until_ts > now_ts:
            continue

        first_failure_ts = int(state.get("first_failure_ts", 0) or 0) or now_ts
        failure_count = int(state.get("failure_count", 0) or 0) + 1
        next_state = {
            "first_failure_ts": first_failure_ts,
            "failure_count": failure_count,
            "locked_until_ts": 0,
        }

        if failure_count >= config["limit"]:
            next_state["locked_until_ts"] = now_ts + config["lockout_seconds"]
            next_state["failure_count"] = config["limit"]

        _write_state(
            key,
            next_state,
            window_seconds=config["window_seconds"],
            lockout_seconds=config["lockout_seconds"],
        )

    return get_login_throttle_status(request, username)


def clear_login_failures(request, username: str) -> None:
    for key in _candidate_keys(request, username):
        cache.delete(key)
