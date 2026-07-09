from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_management, management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from taptrack.pagination import build_query_string, paginate_collection

from .forms import ChecklistForm
from .models import Checklist


def _build_trend(current_value, previous_value, suffix):
    change = current_value - previous_value
    if change > 0:
        return {"label": f"+{change} {suffix}", "direction": "up"}
    if change < 0:
        return {"label": f"{change} {suffix}", "direction": "down"}
    return {"label": f"0 {suffix}", "direction": "flat"}


def _build_chart_points(values):
    highest = max(values) if values else 0
    chart = []
    for index, value in enumerate(values):
        if highest <= 0:
            height = 0
        else:
            height = int(round((value / highest) * 100))
            if value > 0 and height < 8:
                height = 8
        chart.append(
            {
                "height": height,
                "value": value,
                "is_latest": index == len(values) - 1,
            }
        )
    return chart


def _sync_completed_timestamp(task):
    if task.completed and not task.completed_at:
        task.completed_at = timezone.now()
    if not task.completed:
        task.completed_at = None


@login_required
def list_checklists(request):
    today = timezone.localdate()
    selected_type = request.GET.get("type", "")
    selected_status = request.GET.get("status", "")
    selected_preset = request.GET.get("preset", "")
    query = request.GET.get("q", "").strip()

    tasks_qs = Checklist.objects.select_related("assigned_to", "created_by")

    if not is_management(request.user):
        tasks_qs = tasks_qs.filter(assigned_to=request.user)

    if selected_preset == "overdue":
        tasks_qs = tasks_qs.filter(completed=False, due_date__lt=today)
    elif selected_preset == "today":
        tasks_qs = tasks_qs.filter(completed=False, due_date=today)
    elif selected_preset == "completed":
        tasks_qs = tasks_qs.filter(completed=True)

    if selected_type and selected_type in Checklist.ChecklistType.values:
        tasks_qs = tasks_qs.filter(checklist_type=selected_type)

    if selected_status == "pending":
        tasks_qs = tasks_qs.filter(completed=False)
    elif selected_status == "completed":
        tasks_qs = tasks_qs.filter(completed=True)

    if query:
        tasks_qs = tasks_qs.filter(
            Q(title__icontains=query)
            | Q(notes__icontains=query)
            | Q(assigned_to__username__icontains=query)
        )

    scope_qs = tasks_qs
    tasks_qs = tasks_qs.order_by("completed", "due_date", "created_at")
    page_obj = paginate_collection(request, tasks_qs, per_page=12)
    tasks = list(page_obj.object_list)
    week_ago = today - timedelta(days=7)
    previous_week_start = week_ago - timedelta(days=7)
    previous_week_end = week_ago - timedelta(days=1)
    last_seven_dates = [today - timedelta(days=6 - offset) for offset in range(7)]

    total = scope_qs.count()
    completed_count = scope_qs.filter(completed=True).count()
    completion_rate = int((completed_count / total) * 100) if total else 0
    due_today_count = scope_qs.filter(due_date=today, completed=False).count()
    overdue_count = scope_qs.filter(due_date__lt=today, completed=False).count()
    unassigned_count = (
        scope_qs.filter(assigned_to__isnull=True, completed=False).count()
        if is_management(request.user)
        else 0
    )
    completed_week_count = scope_qs.filter(
        completed=True,
        completed_at__date__gte=week_ago,
    ).count()
    completed_previous_week_count = scope_qs.filter(
        completed=True,
        completed_at__date__range=(previous_week_start, previous_week_end),
    ).count()

    created_series = [scope_qs.filter(created_at__date=day).count() for day in last_seven_dates]
    due_series = [
        scope_qs.filter(due_date=day, completed=False).count() for day in last_seven_dates
    ]
    overdue_series = [
        scope_qs.filter(completed=False, due_date__lt=day + timedelta(days=1)).count()
        for day in last_seven_dates
    ]
    completed_series = [
        scope_qs.filter(completed=True, completed_at__date=day).count()
        for day in last_seven_dates
    ]

    filters_active = bool(query or selected_type or selected_status or selected_preset)
    active_filter_count = sum(
        bool(value) for value in [query, selected_type, selected_status, selected_preset]
    )

    selected_type_label = dict(Checklist.ChecklistType.choices).get(selected_type, "")
    status_choices = [
        ("pending", "Pending"),
        ("completed", "Completed"),
    ]
    selected_status_label = dict(status_choices).get(selected_status, "")
    preset_choices = {
        "overdue": "Overdue",
        "today": "Today",
        "completed": "Completed",
    }
    selected_preset_label = preset_choices.get(selected_preset, "")

    if overdue_count:
        queue_state_label = "Needs intervention"
        queue_state_copy = f"{overdue_count} overdue task(s) need immediate follow-up."
        queue_state_tone = "alert"
    elif due_today_count:
        queue_state_label = "Active today"
        queue_state_copy = f"{due_today_count} task(s) are due in the current shift window."
        queue_state_tone = "warn"
    else:
        queue_state_label = "Under control"
        queue_state_copy = "No overdue backlog and no tasks due today."
        queue_state_tone = "ok"

    hero_signals = [
        {
            "label": "Queue health",
            "value": queue_state_label,
            "copy": queue_state_copy,
            "tone": queue_state_tone,
        },
        {
            "label": "Weekly output",
            "value": f"{completed_week_count} closed",
            "copy": _build_trend(
                completed_week_count,
                completed_previous_week_count,
                "vs previous 7 days",
            )["label"],
            "tone": "ok",
        },
        {
            "label": "Control mode",
            "value": "Assignment control" if is_management(request.user) else "Personal execution",
            "copy": (
                "Managers can rebalance ownership and clean up blockers."
                if is_management(request.user)
                else "Only your assigned tasks are shown in this queue."
            ),
            "tone": "neutral",
        },
    ]

    attention_items = []
    if overdue_count:
        attention_items.append(
            {
                "label": "Overdue tasks",
                "value": f"{overdue_count} overdue",
                "copy": "These tasks have already slipped and need immediate completion or reassignment.",
                "tone": "alert",
                "action_label": "Open overdue",
                "url_name": "checklists:list",
                "query": "preset=overdue",
            }
        )
    if due_today_count:
        attention_items.append(
            {
                "label": "Due today",
                "value": f"{due_today_count} due",
                "copy": "These tasks should close before the current operating day ends.",
                "tone": "warn",
                "action_label": "Open today",
                "url_name": "checklists:list",
                "query": "preset=today",
            }
        )
    if is_management(request.user) and unassigned_count:
        attention_items.append(
            {
                "label": "Unassigned work",
                "value": f"{unassigned_count} unassigned",
                "copy": "Ownership is missing on active tasks, which weakens accountability.",
                "tone": "warn",
                "action_label": "Assign tasks",
                "url_name": "checklists:add",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Attention rail",
                "value": "Queue clear",
                "copy": "No overdue blockers are showing inside the current checklist scope.",
                "tone": "ok",
                "action_label": "Assign task" if is_management(request.user) else "Open pending",
                "url_name": "checklists:add" if is_management(request.user) else "checklists:list",
                "query": None if is_management(request.user) else "status=pending",
            }
        )

    filter_presets = [
        {"key": "overdue", "label": "Overdue", "query": "preset=overdue"},
        {"key": "today", "label": "Today", "query": "preset=today"},
        {"key": "completed", "label": "Completed", "query": "preset=completed"},
    ]
    for preset in filter_presets:
        preset["active"] = preset["key"] == selected_preset

    for task in tasks:
        task.assignee_label = task.assigned_to.username if task.assigned_to else "Unassigned"
        if task.completed:
            task.status_label = "Completed"
            task.status_badge_class = "stock-badge-ok"
            task.due_state_label = "Closed"
            task.due_badge_class = "badge-due-completed"
            task.row_tone = "ok"
        elif task.due_date < today:
            task.status_label = "Pending"
            task.status_badge_class = "stock-badge-low"
            task.due_state_label = "Overdue"
            task.due_badge_class = "badge-due-overdue"
            task.row_tone = "alert"
        elif task.due_date == today:
            task.status_label = "Pending"
            task.status_badge_class = "stock-badge-low"
            task.due_state_label = "Due today"
            task.due_badge_class = "badge-due-today"
            task.row_tone = "warn"
        else:
            task.status_label = "Pending"
            task.status_badge_class = "badge-stock-watch"
            task.due_state_label = "Upcoming"
            task.due_badge_class = "badge-due-upcoming"
            task.row_tone = "neutral"

    context = {
        "tasks": tasks,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "task_count": total,
        "due_today_count": due_today_count,
        "overdue_count": overdue_count,
        "unassigned_count": unassigned_count,
        "completed_week_count": completed_week_count,
        "completed_previous_week_count": completed_previous_week_count,
        "completion_rate": completion_rate,
        "type_choices": Checklist.ChecklistType.choices,
        "selected_type": selected_type,
        "selected_type_label": selected_type_label,
        "selected_status": selected_status,
        "selected_status_label": selected_status_label,
        "selected_preset": selected_preset,
        "selected_preset_label": selected_preset_label,
        "query": query,
        "status_choices": status_choices,
        "filters_active": filters_active,
        "active_filter_count": active_filter_count,
        "filter_presets": filter_presets,
        "attention_items": attention_items,
        "hero_signals": hero_signals,
        "completion_trend": _build_trend(
            completed_week_count,
            completed_previous_week_count,
            "vs previous 7 days",
        ),
        "created_chart": _build_chart_points(created_series),
        "due_chart": _build_chart_points(due_series),
        "overdue_chart": _build_chart_points(overdue_series),
        "completion_chart": _build_chart_points(completed_series),
    }
    return render(request, "checklists/list.html", context)


@management_required
def add_checklist(request):
    if request.method == "POST":
        form = ChecklistForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            _sync_completed_timestamp(task)
            task.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=task,
                summary=f"Assigned checklist task: {task.title}",
                details={"assigned_to": task.assigned_to_id, "due_date": str(task.due_date)},
            )
            messages.success(request, "Checklist task assigned.")
            return redirect("checklists:list")
    else:
        form = ChecklistForm()

    return render(
        request,
        "checklists/form.html",
        {
            "form": form,
            "page_title": "Assign Checklist Task",
            "submit_label": "Assign Task",
        },
    )


@management_required
def edit_checklist(request, pk):
    task = get_object_or_404(Checklist, pk=pk)

    if request.method == "POST":
        form = ChecklistForm(request.POST, instance=task)
        if form.is_valid():
            task = form.save(commit=False)
            _sync_completed_timestamp(task)
            task.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.UPDATE,
                target=task,
                summary=f"Updated checklist task: {task.title}",
                details={"completed": task.completed, "due_date": str(task.due_date)},
            )
            messages.success(request, "Checklist task updated.")
            return redirect("checklists:list")
    else:
        form = ChecklistForm(instance=task)

    return render(
        request,
        "checklists/form.html",
        {
            "form": form,
            "page_title": f"Edit {task.title}",
            "submit_label": "Save Changes",
            "task": task,
        },
    )


@login_required
def toggle_complete(request, pk):
    task = get_object_or_404(Checklist, pk=pk)

    if not is_management(request.user) and task.assigned_to_id != request.user.id:
        messages.error(request, "You can only update tasks assigned to you.")
        return redirect("checklists:list")

    if request.method == "POST":
        task.completed = not task.completed
        _sync_completed_timestamp(task)
        task.save(update_fields=["completed", "completed_at", "updated_at"])
        record_audit_event(
            request,
            action=AuditEvent.Action.TOGGLE,
            target=task,
            summary=f"Toggled checklist status: {task.title}",
            details={"completed": task.completed},
        )
        messages.success(request, "Checklist status updated.")

    return redirect("checklists:list")


@management_required
def delete_checklist(request, pk):
    task = get_object_or_404(Checklist, pk=pk)

    if request.method == "POST":
        record_audit_event(
            request,
            action=AuditEvent.Action.DELETE,
            target=task,
            summary=f"Deleted checklist task: {task.title}",
        )
        task.delete()
        messages.success(request, "Checklist task deleted.")
        return redirect("checklists:list")

    return render(request, "checklists/confirm_delete.html", {"task": task})
