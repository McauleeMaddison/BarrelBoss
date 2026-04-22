import json
import logging

from django.conf import settings
from django.urls import reverse

from .models import PushSubscription

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - optional runtime dependency
    webpush = None

    class WebPushException(Exception):
        pass


logger = logging.getLogger(__name__)


def push_notifications_configured():
    return bool(
        webpush
        and settings.WEB_PUSH_PUBLIC_KEY
        and settings.WEB_PUSH_PRIVATE_KEY
        and settings.WEB_PUSH_SUBJECT
    )


def upsert_push_subscription(user, subscription, user_agent=""):
    endpoint = (subscription or {}).get("endpoint")
    keys = (subscription or {}).get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        raise ValueError("Invalid push subscription payload.")

    push_subscription, _ = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": (user_agent or "")[:255],
            "is_active": True,
        },
    )
    return push_subscription


def unsubscribe_push_subscription(user, endpoint=None):
    query = PushSubscription.objects.filter(user=user)
    if endpoint:
        query = query.filter(endpoint=endpoint)
    deleted_count, _ = query.delete()
    return deleted_count


def _build_shift_push_payload(shift, actor_name, event_type):
    shift_window = (
        f"{shift.shift_date:%a %d %b} "
        f"{shift.start_time.strftime('%H:%M')}-{shift.end_time.strftime('%H:%M')}"
    )
    if event_type == "updated":
        body = f"{actor_name} updated your shift: {shift_window}."
    else:
        body = f"{actor_name} assigned a new shift: {shift_window}."

    return {
        "title": "BarrelBoss Shift Update",
        "body": body,
        "icon": "/static/images/pwa-192.png",
        "badge": "/static/images/pwa-192.png",
        "url": reverse("shifts:list"),
        "tag": f"shift-{shift.pk}",
        "renotify": True,
        "data": {
            "kind": "shift_update",
            "shiftId": shift.pk,
        },
    }


def send_shift_push_notification(shift, actor=None, event_type="assigned"):
    if not push_notifications_configured():
        return 0

    profile = getattr(shift.staff, "staff_profile", None)
    if profile and not profile.notify_on_shift_assignment:
        return 0

    subscriptions = PushSubscription.objects.filter(user=shift.staff, is_active=True)
    if not subscriptions.exists():
        return 0

    actor_name = getattr(actor, "username", None) or "Your manager"
    payload = json.dumps(_build_shift_push_payload(shift, actor_name, event_type))
    sent_count = 0

    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=subscription.webpush_payload,
                data=payload,
                vapid_private_key=settings.WEB_PUSH_PRIVATE_KEY,
                vapid_claims={"sub": settings.WEB_PUSH_SUBJECT},
                ttl=86400,
            )
            sent_count += 1
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 410}:
                subscription.delete()
                continue

            logger.warning(
                "Push notification failed for user=%s endpoint=%s: %s",
                shift.staff_id,
                subscription.endpoint,
                exc,
            )
        except Exception as exc:  # pragma: no cover - protects shift flow
            logger.exception(
                "Unexpected push notification error for user=%s endpoint=%s: %s",
                shift.staff_id,
                subscription.endpoint,
                exc,
            )

    return sent_count
