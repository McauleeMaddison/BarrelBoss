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


def _format_delta(current_value, previous_value, suffix):
    change = current_value - previous_value
    if change > 0:
        prefix = f"+{change}"
    elif change < 0:
        prefix = str(change)
    else:
        prefix = "0"
    return f"{prefix} {suffix}"


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

    metrics = [
        {
            "label": "Low Stock Items",
            "value": low_stock_count,
            "tone": "alert",
            "delta": (
                "Inventory healthy this week"
                if low_stock_count == 0
                else f"{low_stock_count} item(s) require replenishment"
            ),
            "note": "Prioritize supplier orders for urgent lines",
        },
        {
            "label": "Order Requests Awaiting Approval",
            "value": pending_order_count,
            "tone": "warn",
            "delta": _format_delta(pending_order_count, pending_order_prev, "vs previous 7 days"),
            "note": "Review draft staff requests before supplier cut-off",
        },
        {
            "label": "Shifts Scheduled This Week",
            "value": shifts_this_week,
            "tone": "ok",
            "delta": _format_delta(shifts_this_week, shifts_last_week, "vs last week"),
            "note": "Keep staffing aligned to expected service load",
        },
        {
            "label": "Breakages This Week",
            "value": breakages_this_week,
            "tone": "neutral",
            "delta": _format_delta(breakages_this_week, breakages_last_week, "vs previous 7 days"),
            "note": "Track recurring loss patterns and replacement costs",
        },
    ]

    quick_actions = [
        {
            "title": "Review Order Requests",
            "url_name": "orders:list",
            "meta": "Approve, update status, and track deliveries.",
        },
        {
            "title": "Manage Shift Hours",
            "url_name": "shifts:list",
            "meta": "Adjust planned and worked shift times.",
        },
        {
            "title": "Review Suppliers",
            "url_name": "suppliers:list",
            "meta": "Update contacts and ordering categories.",
        },
    ]

    focus_list = []
    next_draft = order_qs.filter(status=Order.Status.DRAFT).order_by("created_at").first()
    if next_draft:
        focus_list.append(
            {
                "task": f"Approve {next_draft.reference} request",
                "owner": next_draft.created_by.username if next_draft.created_by else "Staff",
                "due": next_draft.created_at.astimezone(timezone.get_current_timezone()).strftime("%H:%M"),
                "state": "Pending",
            }
        )

    overdue_task = checklist_qs.filter(completed=False, due_date__lt=today).order_by("due_date").first()
    if overdue_task:
        focus_list.append(
            {
                "task": f"Resolve overdue checklist: {overdue_task.title}",
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
                "task": f"Track delivery for {due_delivery.reference}",
                "owner": due_delivery.supplier.name,
                "due": due_delivery.delivery_date.strftime("%d %b"),
                "state": "Scheduled",
            }
        )

    if not focus_list:
        focus_list.append(
            {
                "task": "No urgent operational blockers",
                "owner": "System",
                "due": "Today",
                "state": "Clear",
            }
        )

    activity_events = []
    for order in order_qs.order_by("-updated_at")[:5]:
        activity_events.append(
            {
                "moment": order.updated_at,
                "category": "orders",
                "text": (
                    f"{order.reference} is {order.get_status_display().lower()} "
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
                    f"Shift updated for {shift.staff.username} on {shift.shift_date:%d %b} "
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
                "text": f"Checklist {status_label}: {task.title}",
            }
        )

    for record in breakage_qs.order_by("-created_at")[:5]:
        activity_events.append(
            {
                "moment": record.created_at,
                "category": "breakages",
                "text": (
                    f"{record.quantity} {record.item_name} logged as "
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
                "text": "No recent operational events recorded yet.",
                "category": "orders",
            }
        ]

    last_seven_dates = [seven_day_start + timedelta(days=offset) for offset in range(7)]
    service_values = []
    task_values = []
    for day in last_seven_dates:
        service_values.append(
            order_qs.filter(created_at__date=day).count() + shift_qs.filter(shift_date=day).count()
        )
        task_values.append(
            checklist_qs.filter(completed=True, completed_at__date=day).count()
            + breakage_qs.filter(created_at__date=day).count()
        )

    return {
        "portal_title": "Management Portal",
        "overview_heading": "Management Overview",
        "overview_copy": (
            f"{pending_order_count} order request(s) awaiting approval. "
            f"{deliveries_due_today} delivery(ies) due today and {deliveries_due_tomorrow} due tomorrow."
        ),
        "metrics": metrics,
        "activity": activity,
        "quick_actions": quick_actions,
        "focus_list": focus_list,
        "throughput": _build_throughput(
            last_seven_dates,
            service_values=service_values,
            task_values=task_values,
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

    tasks_due_today = my_tasks_qs.filter(due_date=today, completed=False).count()
    tasks_overdue = my_tasks_qs.filter(due_date__lt=today, completed=False).count()

    breakages_this_week = my_breakages_qs.filter(created_at__date__gte=seven_day_start).count()
    breakages_last_week = my_breakages_qs.filter(
        created_at__date__range=(previous_seven_start, previous_seven_end)
    ).count()

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
            "delta": _format_delta(round(hours_this_week), round(hours_last_week), "hours vs last week"),
            "note": next_shift_note,
        },
        {
            "label": "My Open Order Requests",
            "value": open_order_count,
            "tone": "warn",
            "delta": f"{pending_delivery_count} pending delivery",
            "note": "Draft requests can still be edited before approval",
        },
        {
            "label": "My Tasks Due Today",
            "value": tasks_due_today,
            "tone": "neutral",
            "delta": f"{tasks_overdue} overdue",
            "note": "Complete checklists before handover",
        },
        {
            "label": "My Breakages This Week",
            "value": breakages_this_week,
            "tone": "alert",
            "delta": _format_delta(breakages_this_week, breakages_last_week, "vs previous 7 days"),
            "note": "Report and classify incidents before shift end",
        },
    ]

    quick_actions = [
        {
            "title": "Check My Shift Hours",
            "url_name": "shifts:list",
            "meta": "View upcoming shifts and weekly totals.",
        },
        {
            "title": "Create Stock Order Request",
            "url_name": "orders:add",
            "meta": "Submit a draft order for manager approval.",
        },
        {
            "title": "View My Orders",
            "url_name": "orders:list",
            "meta": "Track request status and delivery progress.",
        },
    ]

    focus_list = []
    if next_shift:
        focus_list.append(
            {
                "task": "Prepare for next scheduled shift",
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

    activity_events = []
    for order in my_orders_qs.order_by("-updated_at")[:5]:
        activity_events.append(
            {
                "moment": order.updated_at,
                "category": "orders",
                "text": f"{order.reference} is {order.get_status_display().lower()}",
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
                "text": f"Checklist {task_state}: {task.title}",
            }
        )

    for record in my_breakages_qs.order_by("-created_at")[:5]:
        activity_events.append(
            {
                "moment": record.created_at,
                "category": "breakages",
                "text": f"{record.quantity} {record.item_name} logged ({record.get_issue_type_display()})",
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
                "text": "No recent activity yet. Start by checking shifts or tasks.",
                "category": "shifts",
            }
        ]

    last_seven_dates = [seven_day_start + timedelta(days=offset) for offset in range(7)]
    service_values = []
    task_values = []
    for day in last_seven_dates:
        shifts_for_day = my_shifts_qs.filter(shift_date=day)
        service_values.append(_sum_shift_hours(shifts_for_day))
        task_values.append(
            my_tasks_qs.filter(completed=True, completed_at__date=day).count()
        )

    return {
        "portal_title": "Staff Portal",
        "overview_heading": "Staff Shift Overview",
        "overview_copy": (
            f"{open_order_count} open order request(s). "
            f"{tasks_due_today} task(s) due today and {tasks_overdue} overdue."
        ),
        "metrics": metrics,
        "activity": activity,
        "quick_actions": quick_actions,
        "focus_list": focus_list,
        "throughput": _build_throughput(
            last_seven_dates,
            service_values=service_values,
            task_values=task_values,
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
