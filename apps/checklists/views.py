from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.scoping import current_venue_or_404
from apps.accounts.permissions import active_venue_required, is_management, management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from taptrack.module_ui import build_module_link, build_module_panel, build_module_snapshot
from taptrack.pagination import build_query_string, paginate_collection

from .forms import ChecklistForm
from .models import Checklist


CHECKLIST_LANE_COPY = {
    Checklist.ChecklistType.OPENING: "Opening standards that set the shift up cleanly before service begins.",
    Checklist.ChecklistType.CLOSING: "Closing standards that protect handover quality and tomorrow's open.",
    Checklist.ChecklistType.DELIVERY: "Delivery handling checks that keep supplier drops accountable and traceable.",
    Checklist.ChecklistType.CLEANING: "Cleaning routines that keep the pub floor, back bar, and cellar ready to work.",
}


def _checklists_workspace_url(*, section="checklists-section-board", **params):
    filtered_params = {key: value for key, value in params.items() if value not in {"", None}}
    url = reverse("checklists:list")
    if filtered_params:
        url = f"{url}?{urlencode(filtered_params)}"
    if section:
        url = f"{url}#{section}"
    return url


def _sync_completed_timestamp(task):
    if task.completed and not task.completed_at:
        task.completed_at = timezone.now()
    if not task.completed:
        task.completed_at = None


def _safe_next_url(request, fallback):
    redirect_to = request.POST.get("next") or request.GET.get("next")
    if redirect_to and url_has_allowed_host_and_scheme(
        redirect_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect_to
    return fallback


def _decorate_task(task, *, today, management_view, request_user_id):
    task.assignee_label = task.assigned_to.username if task.assigned_to else "Unassigned"
    task.created_by_label = task.created_by.username if task.created_by else "Team"
    task.can_toggle = management_view or task.assigned_to_id == request_user_id
    task.note_preview = task.notes or "No handover note recorded."
    task.completed_at_label = (
        timezone.localtime(task.completed_at).strftime("%d %b %Y %H:%M")
        if task.completed_at
        else "Open"
    )
    task.quick_action_label = "Reopen task" if task.completed else "Sign off"

    if task.completed:
        task.status_label = "Completed"
        task.status_badge_class = "badge-stock-healthy"
        task.due_state_label = "Closed"
        task.due_badge_class = "badge-due-completed"
        task.row_tone = "ok"
    elif task.due_date < today:
        task.status_label = "Pending"
        task.status_badge_class = "badge-stock-low"
        task.due_state_label = "Overdue"
        task.due_badge_class = "badge-due-overdue"
        task.row_tone = "alert"
    elif task.due_date == today:
        task.status_label = "Pending"
        task.status_badge_class = "badge-stock-low"
        task.due_state_label = "Due today"
        task.due_badge_class = "badge-due-today"
        task.row_tone = "warn"
    elif task.due_date == today + timedelta(days=1):
        task.status_label = "Pending"
        task.status_badge_class = "badge-stock-watch"
        task.due_state_label = "Due tomorrow"
        task.due_badge_class = "badge-due-upcoming"
        task.row_tone = "neutral"
    else:
        task.status_label = "Pending"
        task.status_badge_class = "badge-stock-watch"
        task.due_state_label = "Upcoming"
        task.due_badge_class = "badge-due-upcoming"
        task.row_tone = "neutral"

    return task


@active_venue_required
def list_checklists(request):
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    venue = current_venue_or_404(request)
    management_view = is_management(request.user, request=request)
    selected_type = request.GET.get("type", "")
    selected_status = request.GET.get("status", "")
    selected_preset = request.GET.get("preset", "")
    query = request.GET.get("q", "").strip()

    base_qs = Checklist.objects.select_related("assigned_to", "created_by").filter(venue=venue)

    if not management_view:
        base_qs = base_qs.filter(assigned_to=request.user)

    tasks_qs = base_qs
    activity_qs = base_qs

    if selected_preset == "overdue":
        tasks_qs = tasks_qs.filter(completed=False, due_date__lt=today)
    elif selected_preset == "today":
        tasks_qs = tasks_qs.filter(completed=False, due_date=today)
    elif selected_preset == "completed":
        tasks_qs = tasks_qs.filter(completed=True)

    if selected_type and selected_type in Checklist.ChecklistType.values:
        tasks_qs = tasks_qs.filter(checklist_type=selected_type)
        activity_qs = activity_qs.filter(checklist_type=selected_type)

    if query:
        task_query = (
            Q(title__icontains=query)
            | Q(notes__icontains=query)
            | Q(assigned_to__username__icontains=query)
        )
        tasks_qs = tasks_qs.filter(task_query)
        activity_qs = activity_qs.filter(task_query)

    metrics_qs = tasks_qs
    display_qs = metrics_qs
    if selected_status == "pending":
        display_qs = display_qs.filter(completed=False)
    elif selected_status == "completed":
        display_qs = display_qs.filter(completed=True)

    display_qs = display_qs.order_by("completed", "due_date", "created_at")
    page_obj = paginate_collection(request, display_qs, per_page=12)
    tasks = [
        _decorate_task(
            task,
            today=today,
            management_view=management_view,
            request_user_id=request.user.id,
        )
        for task in page_obj.object_list
    ]
    week_ago = today - timedelta(days=7)

    total = metrics_qs.count()
    visible_task_count = display_qs.count()
    completed_count = metrics_qs.filter(completed=True).count()
    completion_rate = int((completed_count / total) * 100) if total else 0
    due_today_count = metrics_qs.filter(due_date=today, completed=False).count()
    due_tomorrow_count = metrics_qs.filter(due_date=tomorrow, completed=False).count()
    overdue_count = metrics_qs.filter(due_date__lt=today, completed=False).count()
    ready_to_close_count = metrics_qs.filter(due_date__lte=today, completed=False).count()
    unassigned_count = (
        metrics_qs.filter(assigned_to__isnull=True, completed=False).count()
        if management_view
        else 0
    )
    completed_week_count = metrics_qs.filter(
        completed=True,
        completed_at__date__gte=week_ago,
    ).count()

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
                "href": _checklists_workspace_url(preset="overdue"),
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
                "href": _checklists_workspace_url(preset="today"),
            }
        )
    if management_view and unassigned_count:
        attention_items.append(
            {
                "label": "Unassigned work",
                "value": f"{unassigned_count} unassigned",
                "copy": "Ownership is missing on active tasks, which weakens accountability.",
                "tone": "warn",
                "action_label": "Assign tasks",
                "url_name": "checklists:add",
                "href": reverse("checklists:add"),
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Attention rail",
                "value": "Queue clear",
                "copy": "No overdue blockers are showing inside the current checklist scope.",
                "tone": "ok",
                "action_label": "Assign task" if management_view else "Open pending",
                "url_name": "checklists:add" if management_view else "checklists:list",
                "query": None if management_view else "status=pending",
                "href": (
                    reverse("checklists:add")
                    if management_view
                    else _checklists_workspace_url(status="pending")
                ),
            }
        )

    filter_presets = [
        {
            "key": "",
            "label": "All Tasks",
            "query": "",
            "active": not filters_active,
        },
        {
            "key": "overdue",
            "label": "Overdue",
            "query": "preset=overdue",
            "active": selected_preset == "overdue" and not query and not selected_type and not selected_status,
        },
        {
            "key": "today",
            "label": "Today",
            "query": "preset=today",
            "active": selected_preset == "today" and not query and not selected_type and not selected_status,
        },
        {
            "key": "closing",
            "label": "Closing",
            "query": f"type={Checklist.ChecklistType.CLOSING}&status=pending",
            "active": (
                selected_type == Checklist.ChecklistType.CLOSING
                and selected_status == "pending"
                and not query
                and not selected_preset
            ),
        },
        {
            "key": "completed",
            "label": "Completed",
            "query": "preset=completed",
            "active": selected_preset == "completed" and not query and not selected_type and not selected_status,
        },
    ]

    if overdue_count:
        primary_title = "Clear overdue tasks"
        primary_copy = (
            f"{overdue_count} task(s) are already late and should be completed or reassigned before anything else."
        )
        primary_url = _checklists_workspace_url(preset="overdue")
        primary_label = "Open overdue tasks"
    elif ready_to_close_count:
        primary_title = "Work the sign-off queue"
        primary_copy = (
            f"{ready_to_close_count} task(s) are due now and should be closed before they spill into the next handover."
        )
        primary_url = _checklists_workspace_url(preset="today")
        primary_label = "Open due-now tasks"
    elif management_view:
        primary_title = "Assign the next task"
        primary_copy = (
            "The urgent queue is under control, so you can use this time to keep ownership and planning tidy."
        )
        primary_url = reverse("checklists:add")
        primary_label = "Assign task"
    else:
        primary_title = "Review active tasks"
        primary_copy = (
            "There is no urgent backlog showing, so use the live queue to stay ahead of later handover work."
        )
        primary_url = _checklists_workspace_url(status="pending")
        primary_label = "Open pending tasks"

    module_panel = build_module_panel(
        hero_class="checklists-hero",
        kicker="Task Management" if management_view else "Personal Task Queue",
        badge="Operations Checklist" if management_view else "Personal Checklist",
        title=(
            "Keep tasks clear and on time."
            if management_view
            else "See what needs closing before your shift rolls over."
        ),
        copy=(
            "Work today's queue, close overdue items, and keep handover clean."
            if management_view
            else "Work today's queue, clear anything overdue, and keep handover clean."
        ),
        primary_title=primary_title,
        primary_copy=primary_copy,
        primary_url=primary_url,
        primary_label=primary_label,
        utility_links=[
            *(
                [build_module_link("Assign task", reverse("checklists:add"))]
                if management_view
                else []
            ),
            build_module_link(
                "Closing queue",
                _checklists_workspace_url(
                    type=Checklist.ChecklistType.CLOSING,
                    status="pending",
                ),
            ),
            build_module_link("Completed", _checklists_workspace_url(preset="completed")),
        ],
        toolbar_notes=[
            f"{visible_task_count} shown",
            f"{ready_to_close_count} due now",
            f"{completion_rate}% complete",
        ],
    )
    module_snapshots = [
        build_module_snapshot(
            label="Overdue work",
            state="Escalate" if overdue_count else "Clear",
            tone="alert" if overdue_count else "ok",
            value=overdue_count,
            copy=(
                "Tasks already past due date that should be completed or reassigned before they keep compounding into tomorrow's queue."
            ),
            action_label="Open overdue",
            action_url=_checklists_workspace_url(preset="overdue"),
        ),
        build_module_snapshot(
            label="Ready to sign off",
            state="Close now" if ready_to_close_count else "Queue clear",
            tone="warn" if ready_to_close_count else "ok",
            value=ready_to_close_count,
            copy=(
                "Tasks due now across the active queue, which is the fastest read on whether handover is under control."
            ),
            action_label="Open today",
            action_url=_checklists_workspace_url(preset="today"),
        ),
    ]
    if management_view:
        module_snapshots.append(
            build_module_snapshot(
                label="Ownership gaps",
                state="Assign now" if unassigned_count else "Covered",
                tone="warn" if unassigned_count else "ok",
                value=unassigned_count,
                copy=(
                    "Active tasks with no named owner, which is where sign-off accountability usually starts to weaken."
                ),
                action_label="Assign task",
                action_url=reverse("checklists:add"),
            )
        )
    else:
        module_snapshots.append(
            build_module_snapshot(
                label="Weekly output",
                state=f"{completion_rate}% complete",
                tone="ok",
                value=completed_week_count,
                copy=(
                    "Tasks completed in the last 7 days, giving a simple read on whether execution is moving or starting to stall."
                ),
                action_label="View completed",
                action_url=_checklists_workspace_url(preset="completed"),
            )
        )

    completion_lane_cards = []
    for checklist_type, checklist_label in Checklist.ChecklistType.choices:
        lane_qs = metrics_qs.filter(checklist_type=checklist_type)
        lane_total = lane_qs.count()
        lane_open = lane_qs.filter(completed=False).count()
        lane_due_now = lane_qs.filter(completed=False, due_date__lte=today).count()
        lane_completed_week = lane_qs.filter(
            completed=True,
            completed_at__date__gte=week_ago,
        ).count()
        completion_lane_cards.append(
            {
                "label": checklist_label,
                "value": f"{lane_open} open",
                "copy": CHECKLIST_LANE_COPY[checklist_type],
                "note": (
                    f"{lane_due_now} due now · {lane_completed_week} closed 7d"
                    if lane_total
                    else "No tasks in this lane right now"
                ),
                "url": _checklists_workspace_url(type=checklist_type, status="pending"),
            }
        )

    signoff_tasks = [
        _decorate_task(
            task,
            today=today,
            management_view=management_view,
            request_user_id=request.user.id,
        )
        for task in metrics_qs.filter(completed=False).order_by("due_date", "created_at")[:5]
    ]
    recent_signoff_rows = [
        {
            "title": task.title,
            "meta": (
                f"{task.get_checklist_type_display()} · "
                f"{task.assigned_to.username if task.assigned_to else 'Unassigned'}"
            ),
            "note": (
                f"Closed {timezone.localtime(task.completed_at).strftime('%d %b %H:%M')}"
                if task.completed_at
                else "Marked complete"
            ),
            "badge": "Signed off",
            "tone": "ok",
            "href": (
                reverse("checklists:edit", args=[task.pk])
                if management_view
                else _checklists_workspace_url(q=task.title)
            ),
        }
        for task in activity_qs.filter(completed=True)
        .select_related("assigned_to")
        .order_by("-completed_at", "-updated_at")[:4]
    ]

    context = {
        "tasks": tasks,
        "signoff_tasks": signoff_tasks,
        "recent_signoff_rows": recent_signoff_rows,
        "completion_lane_cards": completion_lane_cards,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "task_count": total,
        "visible_task_count": visible_task_count,
        "due_today_count": due_today_count,
        "due_tomorrow_count": due_tomorrow_count,
        "overdue_count": overdue_count,
        "ready_to_close_count": ready_to_close_count,
        "unassigned_count": unassigned_count,
        "completed_week_count": completed_week_count,
        "completion_rate": completion_rate,
        "type_choices": Checklist.ChecklistType.choices,
        "selected_type": selected_type,
        "selected_type_label": selected_type_label,
        "selected_status": selected_status,
        "selected_status_label": selected_status_label,
        "selected_preset": selected_preset,
        "selected_preset_label": next(
            (preset["label"] for preset in filter_presets if preset["active"] and preset["query"]),
            selected_preset_label,
        ),
        "return_path": request.get_full_path(),
        "query": query,
        "status_choices": status_choices,
        "filters_active": filters_active,
        "active_filter_count": active_filter_count,
        "filter_presets": filter_presets,
        "attention_items": attention_items,
        "module_panel": module_panel,
        "module_snapshots": module_snapshots,
    }
    return render(request, "checklists/list.html", context)


@management_required
def add_checklist(request):
    venue = current_venue_or_404(request)
    if request.method == "POST":
        form = ChecklistForm(request.POST, venue=venue)
        if form.is_valid():
            task = form.save(commit=False)
            task.venue = venue
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
        form = ChecklistForm(venue=venue)

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
    venue = current_venue_or_404(request)
    task = get_object_or_404(Checklist, pk=pk, venue=venue)

    if request.method == "POST":
        form = ChecklistForm(request.POST, instance=task, venue=venue)
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
        form = ChecklistForm(instance=task, venue=venue)

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


@active_venue_required
def toggle_complete(request, pk):
    task = get_object_or_404(Checklist, pk=pk, venue=current_venue_or_404(request))

    if not is_management(request.user, request=request) and task.assigned_to_id != request.user.id:
        messages.error(request, "You can only update tasks assigned to you.")
        return redirect(_safe_next_url(request, reverse("checklists:list")))

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

    return redirect(_safe_next_url(request, reverse("checklists:list")))


@management_required
def delete_checklist(request, pk):
    task = get_object_or_404(Checklist, pk=pk, venue=current_venue_or_404(request))

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
