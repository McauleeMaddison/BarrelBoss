from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_management, management_required, role_home_name
from apps.breakages.models import Breakage
from apps.checklists.models import Checklist
from apps.orders.models import Order
from apps.shifts.models import Shift
from apps.stock.models import StockItem


def _greeting_line():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _build_trend(current_value, previous_value, suffix):
    change = current_value - previous_value
    if change > 0:
        return {"label": f"+{change} {suffix}", "direction": "up"}
    if change < 0:
        return {"label": f"{change} {suffix}", "direction": "down"}
    return {"label": f"0 {suffix}", "direction": "flat"}


def _format_activity_time(moment):
    local_moment = timezone.localtime(moment)
    if local_moment.date() == timezone.localdate():
        return local_moment.strftime("%H:%M")
    return local_moment.strftime("%a %H:%M")


def _to_scaled_percentages(values):
    highest = max(values) if values else 0
    if highest <= 0:
        return [0 for _ in values]
    scaled = []
    for value in values:
        height = int(round((value / highest) * 100))
        if value > 0 and height < 8:
            height = 8
        scaled.append(height)
    return scaled


def _build_chart_points(values):
    scaled_values = _to_scaled_percentages(values)
    return [
        {
            "height": scaled_values[index],
            "value": value,
            "is_latest": index == len(values) - 1,
        }
        for index, value in enumerate(values)
    ]


def _build_throughput(last_seven_dates, *, service_values, task_values):
    service_scaled = _to_scaled_percentages(service_values)
    task_scaled = _to_scaled_percentages(task_values)
    points = []
    for index, day in enumerate(last_seven_dates):
        points.append(
            {
                "label": day.strftime("%a"),
                "value": service_scaled[index],
                "task_value": task_scaled[index],
            }
        )
    return points


def _sum_shift_hours(shifts):
    return round(sum(shift.duration_hours for shift in shifts), 1)


def _management_dashboard_payload():
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(days=1)
    seven_day_start = today - timedelta(days=6)
    previous_seven_start = seven_day_start - timedelta(days=7)
    previous_seven_end = seven_day_start - timedelta(days=1)

    stock_qs = StockItem.objects.filter(is_active=True)
    order_qs = Order.objects.select_related("supplier", "created_by")
    shift_qs = Shift.objects.select_related("staff")
    checklist_qs = Checklist.objects.select_related("assigned_to")
    breakage_qs = Breakage.objects.select_related("reported_by")

    low_stock_count = stock_qs.filter(quantity__lte=F("minimum_level")).count()
    pending_order_count = order_qs.filter(status=Order.Status.DRAFT).count()
    pending_order_prev = order_qs.filter(
        status=Order.Status.DRAFT,
        created_at__date__range=(previous_seven_start, previous_seven_end),
    ).count()

    shifts_this_week = shift_qs.filter(shift_date__range=(week_start, week_end)).count()
    shifts_last_week = shift_qs.filter(
        shift_date__range=(last_week_start, last_week_end)
    ).count()

    deliveries_due_today = order_qs.filter(
        delivery_date=today,
        status__in=[Order.Status.ORDERED, Order.Status.PENDING_DELIVERY],
    ).count()
    deliveries_due_tomorrow = order_qs.filter(
        delivery_date=today + timedelta(days=1),
        status__in=[Order.Status.ORDERED, Order.Status.PENDING_DELIVERY],
    ).count()

    breakages_this_week = breakage_qs.filter(created_at__date__gte=seven_day_start).count()
    breakages_last_week = breakage_qs.filter(
        created_at__date__range=(previous_seven_start, previous_seven_end)
    ).count()
    overdue_task_count = checklist_qs.filter(completed=False, due_date__lt=today).count()

    last_seven_dates = [seven_day_start + timedelta(days=offset) for offset in range(7)]
    order_request_series = []
    draft_request_series = []
    shift_series = []
    delivery_series = []
    breakage_series = []
    task_output_series = []
    for day in last_seven_dates:
        order_request_series.append(order_qs.filter(created_at__date=day).count())
        draft_request_series.append(
            order_qs.filter(created_at__date=day, status=Order.Status.DRAFT).count()
        )
        shift_series.append(shift_qs.filter(shift_date=day).count())
        delivery_series.append(
            order_qs.filter(
                delivery_date=day,
                status__in=[Order.Status.ORDERED, Order.Status.PENDING_DELIVERY],
            ).count()
        )
        breakage_series.append(breakage_qs.filter(created_at__date=day).count())
        task_output_series.append(
            checklist_qs.filter(completed=True, completed_at__date=day).count()
            + breakage_qs.filter(created_at__date=day).count()
        )

    metrics = [
        {
            "label": "Low Stock Items",
            "value": low_stock_count,
            "tone": "alert",
            "state": "Restock now" if low_stock_count else "Stable",
            "state_tone": "alert" if low_stock_count else "ok",
            "summary": (
                f"{low_stock_count} item(s) are below minimum level."
                if low_stock_count
                else "No live stock lines are currently below minimum."
            ),
            "trend": {"label": "Live inventory snapshot", "direction": "flat"},
            "note": "Prioritize replenishment orders for critical lines",
            "chart_label": "7d restock demand",
            "chart_points": _build_chart_points(order_request_series),
            "actions": [
                {"label": "Open stock", "url_name": "stock:list"},
                {"label": "Review orders", "url_name": "orders:list"},
            ],
        },
        {
            "label": "Order Requests Awaiting Approval",
            "value": pending_order_count,
            "tone": "warn",
            "state": "Review queue" if pending_order_count else "Queue clear",
            "state_tone": "warn" if pending_order_count else "ok",
            "summary": (
                f"{pending_order_count} request(s) are waiting on approval."
                if pending_order_count
                else "No draft requests are waiting for sign-off."
            ),
            "trend": _build_trend(
                pending_order_count,
                pending_order_prev,
                "vs previous 7 days",
            ),
            "note": "Review draft requests before supplier cut-off",
            "chart_label": "7d approval intake",
            "chart_points": _build_chart_points(draft_request_series),
            "actions": [
                {"label": "Review orders", "url_name": "orders:list"},
            ],
        },
        {
            "label": "Shifts Scheduled This Week",
            "value": shifts_this_week,
            "tone": "ok",
            "state": "Coverage booked" if shifts_this_week else "Needs scheduling",
            "state_tone": "ok" if shifts_this_week else "warn",
            "summary": (
                f"{deliveries_due_today} delivery(ies) land today and {deliveries_due_tomorrow} tomorrow."
            ),
            "trend": _build_trend(shifts_this_week, shifts_last_week, "vs last week"),
            "note": "Keep staffing aligned with expected service demand",
            "chart_label": "7d rota load",
            "chart_points": _build_chart_points(shift_series),
            "actions": [
                {"label": "Open roster", "url_name": "shifts:list"},
            ],
        },
        {
            "label": "Breakages This Week",
            "value": breakages_this_week,
            "tone": "neutral",
            "state": "Investigate" if breakages_this_week else "Quiet week",
            "state_tone": "alert" if breakages_this_week else "ok",
            "summary": (
                "Loss patterns need review before replacement orders go out."
                if breakages_this_week
                else "No new incident pressure has been recorded this week."
            ),
            "trend": _build_trend(
                breakages_this_week,
                breakages_last_week,
                "vs previous 7 days",
            ),
            "note": "Track recurring loss patterns and replacement cost exposure",
            "chart_label": "7d incident flow",
            "chart_points": _build_chart_points(breakage_series),
            "actions": [
                {"label": "Review breakages", "url_name": "breakages:list"},
            ],
        },
    ]

    quick_actions = [
        {
            "title": "Review Order Approvals",
            "url_name": "orders:list",
            "meta": "Approve requests, update status, and track delivery commitments.",
        },
        {
            "title": "Manage Shift Allocation",
            "url_name": "shifts:list",
            "meta": "Adjust planned and recorded shift hours.",
        },
        {
            "title": "Maintain Supplier Data",
            "url_name": "suppliers:list",
            "meta": "Update supplier contacts and procurement categories.",
        },
    ]

    focus_list = []
    next_draft = order_qs.filter(status=Order.Status.DRAFT).order_by("created_at").first()
    if next_draft:
        focus_list.append(
            {
                "task": f"Approve request {next_draft.reference}",
                "owner": next_draft.created_by.username if next_draft.created_by else "Staff",
                "due": next_draft.created_at.astimezone(timezone.get_current_timezone()).strftime("%H:%M"),
                "state": "Pending",
            }
        )

    overdue_task = checklist_qs.filter(completed=False, due_date__lt=today).order_by("due_date").first()
    if overdue_task:
        focus_list.append(
            {
                "task": f"Resolve overdue checklist task: {overdue_task.title}",
                "owner": overdue_task.assigned_to.username if overdue_task.assigned_to else "Unassigned",
                "due": overdue_task.due_date.strftime("%d %b"),
                "state": "Overdue",
            }
        )

    due_delivery = order_qs.filter(
        delivery_date=today,
        status__in=[Order.Status.ORDERED, Order.Status.PENDING_DELIVERY],
    ).order_by("delivery_date", "created_at").first()
    if due_delivery:
        focus_list.append(
            {
                "task": f"Confirm delivery progress for {due_delivery.reference}",
                "owner": due_delivery.supplier.name,
                "due": due_delivery.delivery_date.strftime("%d %b"),
                "state": "Scheduled",
            }
        )

    if not focus_list:
        focus_list.append(
            {
                "task": "No urgent operational blockers identified",
                "owner": "System",
                "due": "Today",
                "state": "Clear",
            }
        )

    attention_items = []
    if overdue_task_count:
        attention_items.append(
            {
                "label": "Overdue tasks",
                "value": f"{overdue_task_count} overdue",
                "copy": "Checklist work has slipped past its due date and needs reassignment or completion.",
                "tone": "alert",
                "action_label": "Open queue",
                "url_name": "checklists:list",
                "query": "preset=overdue",
            }
        )
    if pending_order_count:
        attention_items.append(
            {
                "label": "Pending approvals",
                "value": f"{pending_order_count} waiting",
                "copy": "Draft order requests are still waiting for management sign-off.",
                "tone": "warn",
                "action_label": "Review orders",
                "url_name": "orders:list",
            }
        )
    if deliveries_due_today or deliveries_due_tomorrow:
        attention_items.append(
            {
                "label": "Delivery watch",
                "value": f"{deliveries_due_today + deliveries_due_tomorrow} incoming",
                "copy": (
                    f"{deliveries_due_today} due today and {deliveries_due_tomorrow} due tomorrow."
                ),
                "tone": "warn" if deliveries_due_today else "neutral",
                "action_label": "Review deliveries",
                "url_name": "orders:list",
            }
        )
    if low_stock_count:
        attention_items.append(
            {
                "label": "Restock pressure",
                "value": f"{low_stock_count} low-stock",
                "copy": "Critical inventory lines are already at or below their minimum level.",
                "tone": "alert",
                "action_label": "Open stock",
                "url_name": "stock:list",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Attention rail",
                "value": "No blockers",
                "copy": "Approvals, deliveries, tasks, and inventory pressure are currently under control.",
                "tone": "ok",
                "action_label": "Open dashboard",
                "url_name": "dashboard:management_portal",
            }
        )

    activity_events = []
    for order in order_qs.order_by("-updated_at")[:5]:
        activity_events.append(
            {
                "moment": order.updated_at,
                "category": "orders",
                "text": (
                    f"{order.reference} is now {order.get_status_display().lower()} "
                    f"({order.supplier.name})"
                ),
            }
        )

    for shift in shift_qs.order_by("-updated_at")[:5]:
        activity_events.append(
            {
                "moment": shift.updated_at,
                "category": "shifts",
                "text": (
                    f"Shift updated: {shift.staff.username} on {shift.shift_date:%d %b} "
                    f"({shift.start_time:%H:%M}-{shift.end_time:%H:%M})"
                ),
            }
        )

    for task in checklist_qs.order_by("-updated_at")[:5]:
        status_label = "completed" if task.completed else "updated"
        activity_events.append(
            {
                "moment": task.updated_at,
                "category": "checklists",
                "text": f"Checklist task {status_label}: {task.title}",
            }
        )

    for record in breakage_qs.order_by("-created_at")[:5]:
        activity_events.append(
            {
                "moment": record.created_at,
                "category": "breakages",
                "text": (
                    f"{record.quantity} {record.item_name} recorded as "
                    f"{record.get_issue_type_display().lower()}"
                ),
            }
        )

    activity_events.sort(key=lambda item: item["moment"], reverse=True)
    activity = [
        {
            "time": _format_activity_time(item["moment"]),
            "text": item["text"],
            "category": item["category"],
        }
        for item in activity_events[:8]
    ]
    if not activity:
        activity = [
            {
                "time": "Now",
                "text": "No recent operational events recorded.",
                "category": "orders",
            }
        ]

    service_values = []
    for index, day in enumerate(last_seven_dates):
        service_values.append(
            order_qs.filter(created_at__date=day).count() + shift_qs.filter(shift_date=day).count()
        )

    return {
        "portal_title": "Management Portal",
        "overview_heading": "Management Overview",
        "overview_copy": (
            f"{pending_order_count} order request(s) awaiting approval. "
            f"{deliveries_due_today} delivery(ies) due today and {deliveries_due_tomorrow} due tomorrow."
        ),
        "metrics": metrics,
        "attention_items": attention_items,
        "activity": activity,
        "quick_actions": quick_actions,
        "focus_list": focus_list,
        "throughput": _build_throughput(
            last_seven_dates,
            service_values=service_values,
            task_values=task_output_series,
        ),
    }


def _staff_dashboard_payload(user):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    previous_week_start = week_start - timedelta(days=7)
    previous_week_end = week_start - timedelta(days=1)
    seven_day_start = today - timedelta(days=6)
    previous_seven_start = seven_day_start - timedelta(days=7)
    previous_seven_end = seven_day_start - timedelta(days=1)

    my_shifts_qs = Shift.objects.filter(staff=user).order_by("shift_date", "start_time")
    my_orders_qs = Order.objects.filter(created_by=user).select_related("supplier")
    my_tasks_qs = Checklist.objects.filter(assigned_to=user)
    my_breakages_qs = Breakage.objects.filter(reported_by=user)

    hours_this_week = _sum_shift_hours(
        my_shifts_qs.filter(shift_date__range=(week_start, week_end))
    )
    hours_last_week = _sum_shift_hours(
        my_shifts_qs.filter(shift_date__range=(previous_week_start, previous_week_end))
    )
    next_shift = my_shifts_qs.filter(shift_date__gte=today).first()

    open_order_count = my_orders_qs.filter(
        status__in=[Order.Status.DRAFT, Order.Status.ORDERED, Order.Status.PENDING_DELIVERY]
    ).count()
    pending_delivery_count = my_orders_qs.filter(status=Order.Status.PENDING_DELIVERY).count()
    submitted_orders_this_week = my_orders_qs.filter(
        created_at__date__gte=seven_day_start
    ).count()
    submitted_orders_last_week = my_orders_qs.filter(
        created_at__date__range=(previous_seven_start, previous_seven_end)
    ).count()

    tasks_due_today = my_tasks_qs.filter(due_date=today, completed=False).count()
    tasks_overdue = my_tasks_qs.filter(due_date__lt=today, completed=False).count()
    completed_tasks_this_week = my_tasks_qs.filter(
        completed=True,
        completed_at__date__gte=seven_day_start,
    ).count()
    completed_tasks_last_week = my_tasks_qs.filter(
        completed=True,
        completed_at__date__range=(previous_seven_start, previous_seven_end),
    ).count()

    breakages_this_week = my_breakages_qs.filter(created_at__date__gte=seven_day_start).count()
    breakages_last_week = my_breakages_qs.filter(
        created_at__date__range=(previous_seven_start, previous_seven_end)
    ).count()
    last_seven_dates = [seven_day_start + timedelta(days=offset) for offset in range(7)]
    hours_series = []
    order_request_series = []
    task_completion_series = []
    breakage_series = []
    for day in last_seven_dates:
        hours_series.append(_sum_shift_hours(my_shifts_qs.filter(shift_date=day)))
        order_request_series.append(my_orders_qs.filter(created_at__date=day).count())
        task_completion_series.append(
            my_tasks_qs.filter(completed=True, completed_at__date=day).count()
        )
        breakage_series.append(my_breakages_qs.filter(created_at__date=day).count())

    next_shift_note = (
        f"Next shift: {next_shift.shift_date:%a %d %b}, {next_shift.start_time:%H:%M}"
        if next_shift
        else "No upcoming shift scheduled"
    )
    metrics = [
        {
            "label": "Hours This Week",
            "value": f"{hours_this_week:.1f}",
            "tone": "ok",
            "state": "Next shift booked" if next_shift else "No shift booked",
            "state_tone": "ok" if next_shift else "warn",
            "summary": next_shift_note,
            "trend": _build_trend(
                round(hours_this_week),
                round(hours_last_week),
                "hours vs last week",
            ),
            "note": "Weekly allocation against the previous rota window.",
            "chart_label": "7d rota hours",
            "chart_points": _build_chart_points(hours_series),
            "actions": [
                {"label": "Open roster", "url_name": "shifts:list"},
            ],
        },
        {
            "label": "My Open Order Requests",
            "value": open_order_count,
            "tone": "warn",
            "state": "Needs approval" if open_order_count else "No blockers",
            "state_tone": "warn" if open_order_count else "ok",
            "summary": (
                f"{pending_delivery_count} request(s) are pending delivery."
                if pending_delivery_count
                else "No deliveries are waiting on your follow-through."
            ),
            "trend": _build_trend(
                submitted_orders_this_week,
                submitted_orders_last_week,
                "submitted vs previous 7 days",
            ),
            "note": "Draft requests can still be edited prior to approval",
            "chart_label": "7d order activity",
            "chart_points": _build_chart_points(order_request_series),
            "actions": [
                {"label": "Review orders", "url_name": "orders:list"},
                {"label": "New request", "url_name": "orders:add"},
            ],
        },
        {
            "label": "My Tasks Due Today",
            "value": tasks_due_today,
            "tone": "neutral",
            "state": "Close today" if tasks_due_today or tasks_overdue else "Clear today",
            "state_tone": "warn" if tasks_due_today or tasks_overdue else "ok",
            "summary": (
                f"{tasks_overdue} overdue task(s) still need completion."
                if tasks_overdue
                else "No overdue checklist tasks are carrying into this shift."
            ),
            "trend": _build_trend(
                completed_tasks_this_week,
                completed_tasks_last_week,
                "completed vs previous 7 days",
            ),
            "note": "Complete assigned checklist tasks before handover",
            "chart_label": "7d task output",
            "chart_points": _build_chart_points(task_completion_series),
            "actions": [
                {"label": "Today queue", "url_name": "checklists:list", "query": "preset=today"},
                {"label": "Overdue", "url_name": "checklists:list", "query": "preset=overdue"},
            ],
        },
        {
            "label": "My Breakages This Week",
            "value": breakages_this_week,
            "tone": "alert",
            "state": "Log follow-up" if breakages_this_week else "No incidents",
            "state_tone": "alert" if breakages_this_week else "ok",
            "summary": (
                "Recent incidents still need accurate classification and closure."
                if breakages_this_week
                else "No breakage pressure has been recorded in the last 7 days."
            ),
            "trend": _build_trend(
                breakages_this_week,
                breakages_last_week,
                "vs previous 7 days",
            ),
            "note": "Report and classify incidents before shift end",
            "chart_label": "7d incidents",
            "chart_points": _build_chart_points(breakage_series),
            "actions": [
                {"label": "Review breakages", "url_name": "breakages:list"},
            ],
        },
    ]

    quick_actions = [
        {
            "title": "Review My Shift Hours",
            "url_name": "shifts:list",
            "meta": "View upcoming shifts and weekly totals.",
        },
        {
            "title": "Create Order Request",
            "url_name": "orders:add",
            "meta": "Submit a draft order request for manager approval.",
        },
        {
            "title": "Review My Orders",
            "url_name": "orders:list",
            "meta": "Track request status and expected delivery dates.",
        },
    ]

    focus_list = []
    if next_shift:
        focus_list.append(
            {
                "task": "Prepare for scheduled shift",
                "owner": "You",
                "due": f"{next_shift.shift_date:%d %b} {next_shift.start_time:%H:%M}",
                "state": "Scheduled",
            }
        )

    due_task = my_tasks_qs.filter(completed=False).order_by("due_date", "created_at").first()
    if due_task:
        focus_list.append(
            {
                "task": due_task.title,
                "owner": "You",
                "due": due_task.due_date.strftime("%d %b"),
                "state": "Pending" if due_task.due_date >= today else "Overdue",
            }
        )

    draft_order = my_orders_qs.filter(status=Order.Status.DRAFT).order_by("created_at").first()
    if draft_order:
        focus_list.append(
            {
                "task": f"Submit {draft_order.reference} for approval",
                "owner": "You",
                "due": draft_order.created_at.astimezone(timezone.get_current_timezone()).strftime("%H:%M"),
                "state": "In Progress",
            }
        )

    if not focus_list:
        focus_list.append(
            {
                "task": "No immediate actions pending",
                "owner": "You",
                "due": "Today",
                "state": "Clear",
            }
        )

    attention_items = []
    if tasks_overdue:
        attention_items.append(
            {
                "label": "Overdue tasks",
                "value": f"{tasks_overdue} overdue",
                "copy": "Assigned checklist work is still open beyond its due date.",
                "tone": "alert",
                "action_label": "Open checklist",
                "url_name": "checklists:list",
                "query": "preset=overdue",
            }
        )
    if tasks_due_today:
        attention_items.append(
            {
                "label": "Due today",
                "value": f"{tasks_due_today} due",
                "copy": "These tasks should close before the current shift finishes.",
                "tone": "warn",
                "action_label": "Open today",
                "url_name": "checklists:list",
                "query": "preset=today",
            }
        )
    if open_order_count:
        attention_items.append(
            {
                "label": "Approval queue",
                "value": f"{open_order_count} open request(s)",
                "copy": "Your open orders still need review, delivery follow-through, or sign-off.",
                "tone": "warn",
                "action_label": "Review orders",
                "url_name": "orders:list",
            }
        )
    if next_shift:
        attention_items.append(
            {
                "label": "Upcoming shift",
                "value": f"{next_shift.shift_date:%a %d %b}",
                "copy": f"Starts at {next_shift.start_time:%H:%M}. Keep your task queue clear ahead of handover.",
                "tone": "neutral",
                "action_label": "Open roster",
                "url_name": "shifts:list",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Attention rail",
                "value": "Clear board",
                "copy": "No overdue tasks, no open requests, and no immediate shift blockers are showing.",
                "tone": "ok",
                "action_label": "Open dashboard",
                "url_name": "dashboard:staff_portal",
            }
        )

    activity_events = []
    for order in my_orders_qs.order_by("-updated_at")[:5]:
        activity_events.append(
            {
                "moment": order.updated_at,
                "category": "orders",
                "text": f"{order.reference} is now {order.get_status_display().lower()}",
            }
        )

    for shift in my_shifts_qs.order_by("-updated_at")[:5]:
        activity_events.append(
            {
                "moment": shift.updated_at,
                "category": "shifts",
                "text": (
                    f"Shift on {shift.shift_date:%d %b} "
                    f"({shift.start_time:%H:%M}-{shift.end_time:%H:%M})"
                ),
            }
        )

    for task in my_tasks_qs.order_by("-updated_at")[:5]:
        task_state = "completed" if task.completed else "updated"
        activity_events.append(
            {
                "moment": task.updated_at,
                "category": "checklists",
                "text": f"Checklist task {task_state}: {task.title}",
            }
        )

    for record in my_breakages_qs.order_by("-created_at")[:5]:
        activity_events.append(
            {
                "moment": record.created_at,
                "category": "breakages",
                "text": f"{record.quantity} {record.item_name} recorded ({record.get_issue_type_display()})",
            }
        )

    activity_events.sort(key=lambda item: item["moment"], reverse=True)
    activity = [
        {
            "time": _format_activity_time(item["moment"]),
            "text": item["text"],
            "category": item["category"],
        }
        for item in activity_events[:8]
    ]
    if not activity:
        activity = [
            {
                "time": "Now",
                "text": "No recent activity recorded. Start with shifts or tasks.",
                "category": "shifts",
            }
        ]

    service_values = []
    for day in last_seven_dates:
        service_values.append(_sum_shift_hours(my_shifts_qs.filter(shift_date=day)))

    return {
        "portal_title": "Staff Portal",
        "overview_heading": "Staff Shift Overview",
        "overview_copy": (
            f"{open_order_count} open order request(s). "
            f"{tasks_due_today} task(s) due today and {tasks_overdue} overdue."
        ),
        "metrics": metrics,
        "attention_items": attention_items,
        "activity": activity,
        "quick_actions": quick_actions,
        "focus_list": focus_list,
        "throughput": _build_throughput(
            last_seven_dates,
            service_values=service_values,
            task_values=task_completion_series,
        ),
    }


def _render_portal(request, *, management_view):
    payload = (
        _management_dashboard_payload()
        if management_view
        else _staff_dashboard_payload(request.user)
    )
    return render(
        request,
        "dashboard/home.html",
        {
            **payload,
            "management_view": management_view,
            "greeting": _greeting_line(),
        },
    )


@login_required
def home(request):
    return redirect(role_home_name(request.user))


@login_required
def staff_portal(request):
    if is_management(request.user):
        return redirect("dashboard:management_portal")
    return _render_portal(request, management_view=False)


@management_required
def management_portal(request):
    return _render_portal(request, management_view=True)
