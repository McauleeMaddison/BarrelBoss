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
    action_labels = dict(AuditEvent.Action.choices)
    filters_active = bool(
        query
        or selected_action
        or selected_target
        or selected_range != "7"
    )
    filter_presets = [
        {"label": "Last 7 days", "query": "range=7", "active": selected_range == "7" and not query and not selected_action and not selected_target},
        {"label": "Today", "query": "range=1", "active": selected_range == "1" and not query and not selected_action and not selected_target},
        {"label": "Last 30 days", "query": "range=30", "active": selected_range == "30" and not query and not selected_action and not selected_target},
        {"label": "Deletes", "query": "action=DELETE", "active": selected_action == AuditEvent.Action.DELETE and not query and not selected_target and selected_range == "7"},
        {"label": "Status Updates", "query": "action=STATUS", "active": selected_action == AuditEvent.Action.STATUS and not query and not selected_target and selected_range == "7"},
    ]
    critical_count = events_qs.filter(
        action__in=[AuditEvent.Action.DELETE, AuditEvent.Action.STATUS]
    ).count()
    today_count = events_qs.filter(created_at__date=timezone.localdate()).count()
    attention_items = []
    if critical_count:
        attention_items.append(
            {
                "label": "Critical changes",
                "value": f"{critical_count} events",
                "copy": "Delete and status update events should be the first set reviewed during incident tracing.",
                "tone": "warn",
                "action_label": "Open critical",
                "url_name": "audit:list",
                "query": "action=STATUS",
            }
        )
    if selected_target:
        attention_items.append(
            {
                "label": "Target model focus",
                "value": selected_target,
                "copy": "The log is narrowed to one target model so change tracing stays tight.",
                "tone": "neutral",
                "action_label": "Clear target",
                "url_name": "audit:list",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Audit attention",
                "value": "Trail active",
                "copy": "Use the search and range controls to isolate a sequence of operational changes quickly.",
                "tone": "ok",
                "action_label": "Open trail",
                "url_name": "audit:list",
            }
        )

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
        "today_count": today_count,
        "critical_count": critical_count,
        "selected_action_label": action_labels.get(selected_action, ""),
        "filters_active": filters_active,
        "active_filter_count": sum(
            [
                bool(query),
                bool(selected_action),
                bool(selected_target),
                selected_range != "7",
            ]
        ),
        "selected_preset_label": next(
            (preset["label"] for preset in filter_presets if preset["active"] and preset["query"]),
            "",
        ),
        "filter_presets": filter_presets,
        "attention_items": attention_items,
        "hero_signals": [
            {
                "label": "Visible events",
                "value": events_qs.count(),
                "copy": "Audit entries after applying the active search, range, target, and action filters.",
                "tone": "neutral",
            },
            {
                "label": "Events today",
                "value": today_count,
                "copy": "Fresh accountability activity logged in the current calendar day.",
                "tone": "ok",
            },
            {
                "label": "Critical changes",
                "value": critical_count,
                "copy": "Delete and status events are the quickest path into sensitive operational changes.",
                "tone": "warn" if critical_count else "ok",
            },
        ],
    }
    return render(request, "audit/list.html", context)
