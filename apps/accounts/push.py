import json
import logging

from django.conf import settings
from django.urls import reverse

from .models import PushSubscription, StaffProfile, VenueMembership

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
        "icon": "/static/images/branding/pwa-192.png",
        "badge": "/static/images/branding/pwa-192.png",
        "url": reverse("shifts:list"),
        "tag": f"shift-{shift.pk}",
        "renotify": True,
        "data": {
            "kind": "shift_update",
            "shiftId": shift.pk,
        },
    }


def _build_stock_count_push_payload(item, actor_name):
    quantity_window = f"{item.quantity} {item.get_unit_display().lower()}"
    return {
        "title": "BarrelBoss Stock Count",
        "body": f"{actor_name} counted and confirmed {item.name} ({quantity_window}).",
        "icon": "/static/images/branding/pwa-192.png",
        "badge": "/static/images/branding/pwa-192.png",
        "url": f"{reverse('stock:list')}?focus=uncounted#stock-section-board",
        "tag": f"stock-count-{item.pk}",
        "renotify": True,
        "data": {
            "kind": "stock_count",
            "stockItemId": item.pk,
        },
    }


def _build_checklist_completion_push_payload(task, actor_name):
    return {
        "title": "BarrelBoss Task Completion",
        "body": (
            f"{actor_name} completed {task.title} "
            f"({task.get_checklist_type_display().lower()})."
        ),
        "icon": "/static/images/branding/pwa-192.png",
        "badge": "/static/images/branding/pwa-192.png",
        "url": f"{reverse('checklists:list')}?status=pending#checklists-section-board",
        "tag": f"checklist-complete-{task.pk}",
        "renotify": True,
        "data": {
            "kind": "checklist_completion",
            "checklistTaskId": task.pk,
        },
    }


def send_shift_push_notification(shift, actor=None, event_type="assigned"):
    if not push_notifications_configured():
        return 0

    membership = VenueMembership.objects.filter(
        venue=shift.venue,
        user=shift.staff,
        is_active=True,
    ).first()
    if membership and not membership.notify_on_shift_assignment:
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


def send_stock_count_push_notification(item, actor=None):
    if not push_notifications_configured():
        return 0

    memberships = VenueMembership.objects.filter(
        venue=item.venue,
        is_active=True,
        role__in=[StaffProfile.Role.MANAGER, StaffProfile.Role.LANDLORD],
    ).select_related("user")
    if actor is not None:
        memberships = memberships.exclude(user=actor)

    recipients = [
        membership.user
        for membership in memberships
        if membership.notify_on_shift_assignment
    ]
    if not recipients:
        return 0

    subscriptions = PushSubscription.objects.filter(user__in=recipients, is_active=True).select_related("user")
    if not subscriptions.exists():
        return 0

    actor_name = getattr(actor, "username", None) or "A team member"
    payload = json.dumps(_build_stock_count_push_payload(item, actor_name))
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
                "Stock count push notification failed for user=%s endpoint=%s: %s",
                subscription.user_id,
                subscription.endpoint,
                exc,
            )
        except Exception as exc:  # pragma: no cover - protects stock count flow
            logger.exception(
                "Unexpected stock count push notification error for user=%s endpoint=%s: %s",
                subscription.user_id,
                subscription.endpoint,
                exc,
            )

    return sent_count


def send_checklist_completion_push_notification(task, actor=None):
    if not push_notifications_configured():
        return 0

    memberships = VenueMembership.objects.filter(
        venue=task.venue,
        is_active=True,
        role__in=[StaffProfile.Role.MANAGER, StaffProfile.Role.LANDLORD],
    ).select_related("user")
    if actor is not None:
        memberships = memberships.exclude(user=actor)

    recipients = [
        membership.user
        for membership in memberships
        if membership.notify_on_shift_assignment
    ]
    if not recipients:
        return 0

    subscriptions = PushSubscription.objects.filter(
        user__in=recipients,
        is_active=True,
    ).select_related("user")
    if not subscriptions.exists():
        return 0

    actor_name = getattr(actor, "username", None) or "A team member"
    payload = json.dumps(_build_checklist_completion_push_payload(task, actor_name))
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
                "Checklist completion push notification failed for user=%s endpoint=%s: %s",
                subscription.user_id,
                subscription.endpoint,
                exc,
            )
        except Exception as exc:  # pragma: no cover - protects checklist completion flow
            logger.exception(
                "Unexpected checklist completion push notification error for user=%s endpoint=%s: %s",
                subscription.user_id,
                subscription.endpoint,
                exc,
            )

    return sent_count
