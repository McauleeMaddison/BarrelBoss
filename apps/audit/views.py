from datetime import timedelta

from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.permissions import management_required
from taptrack.pagination import build_query_string, paginate_collection

from .models import AuditEvent


@management_required
def list_events(request):
    query = (request.GET.get("q") or "").strip()
    selected_action = request.GET.get("action", "")
    selected_target = request.GET.get("target", "")
    selected_range = request.GET.get("range", "7")
    if selected_range not in {"1", "7", "30", "90", "all"}:
        selected_range = "7"

    events_qs = AuditEvent.objects.select_related("actor")

    if selected_range != "all":
        start = timezone.now() - timedelta(days=int(selected_range))
        events_qs = events_qs.filter(created_at__gte=start)

    if selected_action and selected_action in AuditEvent.Action.values:
        events_qs = events_qs.filter(action=selected_action)

    if selected_target:
        events_qs = events_qs.filter(target_model=selected_target)

    if query:
        events_qs = events_qs.filter(
            Q(actor_username__icontains=query)
            | Q(summary__icontains=query)
            | Q(target_model__icontains=query)
            | Q(target_id__icontains=query)
        )

    target_choices = (
        AuditEvent.objects.order_by("target_model")
        .values_list("target_model", flat=True)
        .distinct()
    )

    page_obj = paginate_collection(request, events_qs, per_page=25)
    events = list(page_obj.object_list)

    context = {
        "events": events,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "query": query,
        "selected_action": selected_action,
        "selected_target": selected_target,
        "selected_range": selected_range,
        "action_choices": AuditEvent.Action.choices,
        "target_choices": [value for value in target_choices if value],
        "range_choices": [
            ("1", "Last 24 hours"),
            ("7", "Last 7 days"),
            ("30", "Last 30 days"),
            ("90", "Last 90 days"),
            ("all", "All time"),
        ],
        "event_count": events_qs.count(),
        "today_count": AuditEvent.objects.filter(created_at__date=timezone.localdate()).count(),
        "critical_count": AuditEvent.objects.filter(
            action__in=[AuditEvent.Action.DELETE, AuditEvent.Action.STATUS]
        ).count(),
    }
    return render(request, "audit/list.html", context)
