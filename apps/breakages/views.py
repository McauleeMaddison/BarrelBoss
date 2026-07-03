from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from taptrack.pagination import build_query_string, paginate_collection

from .forms import BreakageForm
from .models import Breakage


@login_required
def list_breakages(request):
    query = request.GET.get("q", "").strip()
    selected_issue = request.GET.get("issue", "")

    records_qs = Breakage.objects.select_related("reported_by")

    if query:
        records_qs = records_qs.filter(
            Q(item_name__icontains=query)
            | Q(notes__icontains=query)
            | Q(reported_by__username__icontains=query)
        )

    if selected_issue and selected_issue in Breakage.IssueType.values:
        records_qs = records_qs.filter(issue_type=selected_issue)

    page_obj = paginate_collection(request, records_qs.order_by("-created_at"), per_page=12)
    records = list(page_obj.object_list)
    week_start = timezone.now() - timedelta(days=7)
    week_count = Breakage.objects.filter(created_at__gte=week_start).count()
    issue_labels = dict(Breakage.IssueType.choices)
    filters_active = bool(query or selected_issue)
    filter_presets = [
        {"label": "All Incidents", "query": "", "active": not filters_active},
        *[
            {
                "label": label,
                "query": f"issue={value}",
                "active": selected_issue == value and not query,
            }
            for value, label in Breakage.IssueType.choices
        ],
    ]
    attention_items = []
    if week_count:
        attention_items.append(
            {
                "label": "Recent incidents",
                "value": f"{week_count} in 7d",
                "copy": "Fresh incidents are the quickest signal that a live floor issue may still be repeating.",
                "tone": "alert" if week_count >= 5 else "warn",
                "action_label": "Open log",
                "url_name": "breakages:list",
            }
        )
    if selected_issue:
        attention_items.append(
            {
                "label": "Issue focus",
                "value": issue_labels.get(selected_issue, selected_issue),
                "copy": "The log is narrowed to one issue type so patterns can be inspected more quickly.",
                "tone": "neutral",
                "action_label": "Clear filter",
                "url_name": "breakages:list",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Incident board",
                "value": "Quiet",
                "copy": "No recent breakage pressure is standing out in the current log view.",
                "tone": "ok",
                "action_label": "Log incident",
                "url_name": "breakages:add",
            }
        )

    context = {
        "records": records,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "record_count": records_qs.count(),
        "week_count": week_count,
        "issue_choices": Breakage.IssueType.choices,
        "selected_issue": selected_issue,
        "query": query,
        "filters_active": filters_active,
        "active_filter_count": sum([bool(query), bool(selected_issue)]),
        "selected_issue_label": issue_labels.get(selected_issue, ""),
        "selected_preset_label": next(
            (preset["label"] for preset in filter_presets if preset["active"] and preset["query"]),
            "",
        ),
        "filter_presets": filter_presets,
        "attention_items": attention_items,
    }
    return render(request, "breakages/list.html", context)


@login_required
def add_breakage(request):
    if request.method == "POST":
        form = BreakageForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.reported_by = request.user
            record.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=record,
                summary=f"Logged breakage: {record.item_name}",
                details={
                    "quantity": record.quantity,
                    "issue_type": record.issue_type,
                },
            )
            messages.success(request, "Breakage incident logged.")
            return redirect("breakages:list")
    else:
        form = BreakageForm()

    return render(
        request,
        "breakages/form.html",
        {
            "form": form,
            "page_title": "Log Breakage Incident",
            "submit_label": "Log Incident",
        },
    )


@management_required
def delete_breakage(request, pk):
    record = get_object_or_404(Breakage, pk=pk)

    if request.method == "POST":
        record_audit_event(
            request,
            action=AuditEvent.Action.DELETE,
            target=record,
            summary=f"Deleted breakage record for {record.item_name}",
            details={"issue_type": record.issue_type},
        )
        record.delete()
        messages.success(request, "Breakage record deleted.")
        return redirect("breakages:list")

    return render(request, "breakages/confirm_delete.html", {"record": record})
