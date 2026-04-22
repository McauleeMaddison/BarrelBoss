import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import management_required, role_home_name
from apps.accounts.push import (
    push_notifications_configured,
    unsubscribe_push_subscription,
    upsert_push_subscription,
)
from apps.accounts.models import StaffProfile
from apps.accounts.permissions import is_management


def home_redirect(request):
    if request.user.is_authenticated:
        return redirect(role_home_name(request.user))
    return redirect("login")


@management_required
def staff_page(request):
    team = [
        {"name": "Morgan Doyle", "role": "Manager", "status": "Active"},
        {"name": "Nina Walsh", "role": "Bartender", "status": "Active"},
        {"name": "Elliot Shaw", "role": "Barback", "status": "Inactive"},
    ]
    return render(request, "accounts/staff.html", {"team": team})


@management_required
def reports_page(request):
    report_tiles = [
        "Low Stock Summary",
        "Weekly Usage",
        "Supplier Spend",
        "Breakage Trends",
    ]
    return render(request, "reports/index.html", {"report_tiles": report_tiles})


@login_required
def settings_page(request):
    team_profiles = (
        StaffProfile.objects.select_related("user")
        .filter(is_active=True, role=StaffProfile.Role.STAFF)
        .order_by("user__username")
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "team_shift_alerts":
            if not is_management(request.user):
                messages.error(request, "Only management can update team alert preferences.")
                return redirect("settings")

            updated_count = 0
            for profile in team_profiles:
                should_notify = request.POST.get(f"notify_staff_{profile.user_id}") == "on"
                if profile.notify_on_shift_assignment != should_notify:
                    profile.notify_on_shift_assignment = should_notify
                    profile.save(update_fields=["notify_on_shift_assignment", "updated_at"])
                    updated_count += 1

            if updated_count:
                messages.success(
                    request,
                    f"Saved shift alert preferences for {updated_count} staff member(s).",
                )
            else:
                messages.info(request, "No changes were made to staff alert preferences.")

            return redirect("settings")

        messages.error(request, "Unknown settings action.")
        return redirect("settings")

    context = {
        "team_profiles": team_profiles,
        "push_subscription_count": request.user.push_subscriptions.filter(
            is_active=True
        ).count(),
        "web_push_public_key": settings.WEB_PUSH_PUBLIC_KEY,
        "web_push_configured": push_notifications_configured(),
    }
    return render(request, "settings/index.html", context)


@login_required
@require_POST
def push_subscribe(request):
    if not push_notifications_configured():
        return JsonResponse(
            {
                "ok": False,
                "error": "Push notifications are not configured on this server yet.",
            },
            status=503,
        )

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)

    subscription = payload.get("subscription", payload)
    try:
        upsert_push_subscription(
            request.user,
            subscription,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse({"ok": True})


@login_required
@require_POST
def push_unsubscribe(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON payload."}, status=400)

    endpoint = payload.get("endpoint")
    deleted_count = unsubscribe_push_subscription(request.user, endpoint=endpoint)
    return JsonResponse({"ok": True, "deleted": deleted_count})


@require_GET
def service_worker(request):
    response = HttpResponse(
        render_to_string("service-worker.js"),
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
