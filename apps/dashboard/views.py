from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count, F, Q, Sum
from django.urls import reverse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.scoping import current_venue_or_404
from apps.accounts.permissions import active_venue_required, is_management, management_required, role_home_name
from apps.breakages.models import Breakage
from apps.checklists.models import Checklist
from apps.orders.models import Order
from apps.sales.models import PosIntegration, SalesSnapshot
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


def _build_currency_trend(current_value, previous_value, suffix):
    change = current_value - previous_value
    if change > 0:
        return {"label": f"+£{change:,.0f} {suffix}", "direction": "up"}
    if change < 0:
        return {"label": f"-£{abs(change):,.0f} {suffix}", "direction": "down"}
    return {"label": f"£0 {suffix}", "direction": "flat"}


def _format_activity_time(moment):
    local_moment = timezone.localtime(moment)
    if local_moment.date() == timezone.localdate():
        return local_moment.strftime("%H:%M")
    return local_moment.strftime("%a %H:%M")


def _dashboard_href(url_name, *, args=None, query=None, fragment=None, **params):
    default_fragments = {
        "checklists:list": "checklists-section-board",
        "stock:list": "stock-section-board",
        "shifts:list": "shifts-section-board",
        "orders:list": "orders-section-board",
        "breakages:list": "breakages-section-board",
        "sales:list": "salesTable",
    }
    url = reverse(url_name, args=args or [])
    if query:
        url = f"{url}?{query}"
    else:
        query_params = [
            (key, value)
            for key, value in params.items()
            if value not in (None, "")
        ]
        if query_params:
            url = f"{url}?{urlencode(query_params, doseq=True)}"

    target_fragment = fragment or default_fragments.get(url_name)
    if target_fragment:
        url = f"{url}#{target_fragment}"
    return url


def _normalize_link_item(item):
    if item.get("href") or not item.get("url_name"):
        return item

    normalized = dict(item)
    normalized["href"] = _dashboard_href(
        normalized["url_name"],
        args=normalized.get("args"),
        query=normalized.get("query"),
        fragment=normalized.get("fragment"),
    )
    return normalized


def _normalize_link_items(items):
    return [_normalize_link_item(item) for item in items]


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


def _connector_health_state(integration):
    mapped_count = getattr(integration, "active_mapping_count", 0)
    if not integration.is_enabled:
        return "neutral"
    if integration.last_error_at and (
        not integration.last_success_at or integration.last_error_at >= integration.last_success_at
    ):
        return "alert"
    if mapped_count == 0:
        return "warn"
    if not integration.last_success_at:
        return "warn"
    next_sync_at = integration.last_success_at + timedelta(
        minutes=integration.sync_interval_minutes
    )
    if integration.auto_sync_enabled and next_sync_at <= timezone.now():
        return "warn"
    return "ok"


def _format_short_date(value):
    return value.strftime("%a %d %b")


def _format_short_datetime(value):
    return timezone.localtime(value).strftime("%d %b %H:%M")


def _order_tone(status):
    if status == Order.Status.DRAFT:
        return "warn"
    if status == Order.Status.PENDING_DELIVERY:
        return "warn"
    if status == Order.Status.ORDERED:
        return "neutral"
    if status == Order.Status.DELIVERED:
        return "ok"
    return "alert"


def _stock_row(item):
    shortage = max(item.minimum_level - item.quantity, 0)
    return {
        "title": item.name,
        "meta": (
            f"{item.quantity} {item.get_unit_display().lower()} on hand vs min "
            f"{item.minimum_level}"
        ),
        "note": (
            f"Supplier: {item.supplier.name}"
            if item.supplier
            else "Supplier: Not linked yet"
        ),
        "badge": f"{shortage} short" if shortage else "At minimum",
        "tone": "alert" if item.quantity < item.minimum_level else "warn",
        "href": _dashboard_href("stock:list", q=item.name),
    }


def _order_row(order):
    item_count = getattr(order, "item_count", 0)
    delivery_copy = (
        f"Due {_format_short_date(order.delivery_date)}"
        if order.delivery_date
        else "No delivery date"
    )
    return {
        "title": order.reference,
        "meta": f"{order.supplier.name} · {item_count} line(s) · {delivery_copy}",
        "note": (
            f"Requested by {order.created_by.username}"
            if order.created_by
            else "Requested by team"
        ),
        "badge": order.get_status_display(),
        "tone": _order_tone(order.status),
        "href": _dashboard_href("orders:edit", args=[order.pk]),
    }


def _task_row(task, *, today, management_view):
    if task.due_date < today:
        badge = "Overdue"
        tone = "alert"
    elif task.due_date == today:
        badge = "Due today"
        tone = "warn"
    else:
        badge = "Open"
        tone = "neutral"
    return {
        "title": task.title,
        "meta": f"{task.get_checklist_type_display()} · due {_format_short_date(task.due_date)}",
        "note": (
            f"Assigned to {task.assigned_to.username}"
            if task.assigned_to
            else "Unassigned"
        ),
        "badge": badge,
        "tone": tone,
        "href": (
            _dashboard_href("checklists:edit", args=[task.pk])
            if management_view
            else _dashboard_href(
                "checklists:list",
                q=task.title,
                status="pending" if not task.completed else "completed",
            )
        ),
    }


def _breakage_row(record):
    return {
        "title": f"{record.quantity} x {record.item_name}",
        "meta": (
            f"{record.get_issue_type_display()} · logged "
            f"{_format_short_datetime(record.created_at)}"
        ),
        "note": (
            f"Reported by {record.reported_by.username}"
            if record.reported_by
            else "Reporter not captured"
        ),
        "badge": "Loss log",
        "tone": "warn",
        "href": _dashboard_href(
            "breakages:list",
            q=record.item_name,
            issue=record.issue_type,
        ),
    }


def _integration_row(integration):
    health_state = _connector_health_state(integration)
    last_sync_label = (
        f"Last success {_format_short_datetime(integration.last_success_at)}"
        if integration.last_success_at
        else "No successful sync yet"
    )
    if integration.last_error_at and (
        not integration.last_success_at or integration.last_error_at >= integration.last_success_at
    ):
        last_sync_label = f"Last error {_format_short_datetime(integration.last_error_at)}"
    return {
        "title": integration.label,
        "meta": (
            f"{integration.get_provider_display()} · "
            f"{getattr(integration, 'active_mapping_count', 0)} mapped location(s)"
        ),
        "note": last_sync_label,
        "badge": integration.health_label,
        "tone": health_state,
        "href": _dashboard_href("sales:integration_edit", args=[integration.pk]),
    }


def _shift_row(shift, *, today, management_view):
    if shift.shift_date == today:
        badge = "Today"
        tone = "warn"
    else:
        badge = "Upcoming"
        tone = "neutral"
    return {
        "title": _format_short_date(shift.shift_date),
        "meta": (
            f"{shift.start_time:%H:%M}-{shift.end_time:%H:%M} · "
            f"{shift.duration_hours:.1f}h scheduled"
        ),
        "note": shift.notes or "No shift notes attached",
        "badge": badge,
        "tone": tone,
        "href": (
            _dashboard_href("shifts:edit", args=[shift.pk])
            if management_view
            else _dashboard_href("shifts:list", query="range=upcoming")
        ),
    }


def _management_dashboard_payload(venue):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(days=1)
    seven_day_start = today - timedelta(days=6)
    previous_seven_start = seven_day_start - timedelta(days=7)
    previous_seven_end = seven_day_start - timedelta(days=1)

    stock_qs = StockItem.objects.filter(venue=venue, is_active=True)
    order_qs = Order.objects.select_related("supplier", "created_by").filter(venue=venue)
    shift_qs = Shift.objects.select_related("staff").filter(venue=venue)
    checklist_qs = Checklist.objects.select_related("assigned_to").filter(venue=venue)
    breakage_qs = Breakage.objects.select_related("reported_by").filter(venue=venue)
    sales_qs = SalesSnapshot.objects.filter(venue=venue)
    pos_integrations = list(
        PosIntegration.objects.filter(venue=venue).annotate(
            active_mapping_count=Count(
                "location_mappings",
                filter=Q(location_mappings__is_active=True),
                distinct=True,
            )
        ).order_by("label")
    )

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
    today_sales_snapshot = sales_qs.filter(business_date=today).order_by("-synced_at").first()
    latest_sales_snapshot = sales_qs.order_by("-business_date", "-synced_at", "-id").first()
    net_sales_today = (
        sales_qs.filter(business_date=today).aggregate(total=Sum("net_sales")).get("total")
        or 0
    )
    net_sales_previous_seven = (
        sales_qs.filter(
            business_date__range=(previous_seven_start, previous_seven_end)
        ).aggregate(total=Sum("net_sales")).get("total")
        or 0
    )
    net_sales_this_seven = (
        sales_qs.filter(
            business_date__range=(seven_day_start, today)
        ).aggregate(total=Sum("net_sales")).get("total")
        or 0
    )
    covers_today = (
        sales_qs.filter(business_date=today).aggregate(total=Sum("covers")).get("total")
        or 0
    )
    today_labor_hours = _sum_shift_hours(shift_qs.filter(shift_date=today))
    active_connector_count = sum(1 for integration in pos_integrations if integration.is_enabled)
    mapped_location_count = sum(
        getattr(integration, "active_mapping_count", 0) for integration in pos_integrations
    )
    connectors_needing_attention = sum(
        1 for integration in pos_integrations if _connector_health_state(integration) != "ok"
    )

    breakages_this_week = breakage_qs.filter(created_at__date__gte=seven_day_start).count()
    breakages_last_week = breakage_qs.filter(
        created_at__date__range=(previous_seven_start, previous_seven_end)
    ).count()
    overdue_task_count = checklist_qs.filter(completed=False, due_date__lt=today).count()
    tasks_due_today_count = checklist_qs.filter(completed=False, due_date=today).count()
    low_stock_barrel_count = stock_qs.filter(
        quantity__lte=F("minimum_level"),
        category=StockItem.Category.BEER_BARRELS,
    ).count()

    last_seven_dates = [seven_day_start + timedelta(days=offset) for offset in range(7)]
    order_request_series = []
    draft_request_series = []
    shift_series = []
    delivery_series = []
    breakage_series = []
    task_output_series = []
    sales_series = []
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
        sales_series.append(
            sales_qs.filter(business_date=day).aggregate(total=Sum("net_sales")).get("total")
            or 0
        )

    metrics = [
        {
            "label": "Net Sales Today",
            "value": f"£{net_sales_today:,.0f}",
            "tone": "ok",
            "state": (
                "Live sync"
                if today_sales_snapshot
                and today_sales_snapshot.sync_mode == SalesSnapshot.SyncMode.LIVE
                else "Needs sync" if not today_sales_snapshot else "Manual close"
            ),
            "state_tone": (
                "ok"
                if today_sales_snapshot
                and today_sales_snapshot.sync_mode == SalesSnapshot.SyncMode.LIVE
                else "warn"
            ),
            "summary": (
                f"{today_sales_snapshot.transactions} transaction(s) across {covers_today} covers."
                if today_sales_snapshot
                else "No daily sales snapshot has landed for today yet."
            ),
            "trend": _build_currency_trend(
                net_sales_this_seven,
                net_sales_previous_seven,
                "vs previous 7 days",
            ),
            "note": (
                f"Sales per labor hour is £{(net_sales_today / Decimal(str(today_labor_hours))):,.0f}."
                if today_labor_hours and net_sales_today
                else "Connect live trade back into rota and stock decisions."
            ),
            "chart_label": "7d sales pulse",
            "chart_points": _build_chart_points(sales_series),
            "actions": [
                {"label": "Open sales", "url_name": "sales:list"},
                {"label": "Sync center", "url_name": "sales:sync_center"},
            ],
        },
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
    ]

    low_stock_preview = [
        _stock_row(item)
        for item in stock_qs.filter(quantity__lte=F("minimum_level"))
        .select_related("supplier")
        .order_by("quantity", "minimum_level", "name")[:4]
    ]
    draft_order_preview = list(
        order_qs.filter(status=Order.Status.DRAFT)
        .annotate(item_count=Count("items", distinct=True))
        .order_by("created_at")[:2]
    )
    delivery_order_preview = list(
        order_qs.filter(status__in=[Order.Status.ORDERED, Order.Status.PENDING_DELIVERY])
        .annotate(item_count=Count("items", distinct=True))
        .order_by("delivery_date", "created_at")[:2]
    )
    order_queue_preview = [_order_row(order) for order in draft_order_preview + delivery_order_preview]
    service_preview = [_integration_row(integration) for integration in pos_integrations[:4]]
    if not service_preview and latest_sales_snapshot:
        service_preview = [
            {
                "title": f"{latest_sales_snapshot.location_name} sales snapshot",
                "meta": (
                    f"£{latest_sales_snapshot.net_sales:,.0f} on "
                    f"{_format_short_date(latest_sales_snapshot.business_date)}"
                ),
                "note": (
                    f"{latest_sales_snapshot.transactions} transaction(s) · "
                    f"{latest_sales_snapshot.covers} covers"
                ),
                "badge": latest_sales_snapshot.get_sync_mode_display(),
                "tone": "ok"
                if latest_sales_snapshot.sync_mode == SalesSnapshot.SyncMode.LIVE
                else "warn",
                "href": _dashboard_href("sales:list"),
            }
        ]
    standards_preview = [
        *[
            _task_row(task, today=today, management_view=True)
            for task in checklist_qs.filter(completed=False, due_date__lte=today)
            .order_by("due_date", "created_at")[:2]
        ],
        *[_breakage_row(record) for record in breakage_qs.order_by("-created_at")[:2]],
    ]

    portal_sections = [
        {
            "slug": "cellar",
            "label": "Cellar watch",
            "eyebrow": "Cellar pressure",
            "title": "Cellar gaps and restock pressure",
            "copy": "Check the live shortages first, then decide whether orders need moving today.",
            "stats": [
                {"label": "Low-stock lines", "value": low_stock_count},
                {"label": "Beer barrels low", "value": low_stock_barrel_count},
                {"label": "Deliveries today", "value": deliveries_due_today},
            ],
            "rows": low_stock_preview,
            "empty_state": "No cellar or back-bar lines are currently below minimum.",
            "actions": [
                {"label": "Open stock", "url_name": "stock:list"},
                {"label": "Review orders", "url_name": "orders:list"},
            ],
        },
        {
            "slug": "orders",
            "label": "Delivery queue",
            "eyebrow": "Approvals and inbound",
            "title": "Approvals and incoming deliveries",
            "copy": "Keep draft sign-off and inbound stock in one board instead of bouncing between screens.",
            "stats": [
                {"label": "Awaiting approval", "value": pending_order_count},
                {"label": "Due today", "value": deliveries_due_today},
                {"label": "Due tomorrow", "value": deliveries_due_tomorrow},
            ],
            "rows": order_queue_preview,
            "empty_state": "No active approval or delivery queue is showing right now.",
            "actions": [
                {"label": "Open orders", "url_name": "orders:list"},
                {"label": "Create order", "url_name": "orders:add"},
            ],
        },
        {
            "slug": "trade",
            "label": "Trade pulse",
            "eyebrow": "Sales and sync",
            "title": "Trade pace and sync health",
            "copy": "Use sales, covers, and feed status here before changing rota or ordering decisions.",
            "stats": [
                {"label": "Net sales today", "value": f"£{net_sales_today:,.0f}"},
                {"label": "Covers today", "value": covers_today},
                {"label": "Labor today", "value": f"{today_labor_hours:.1f}h"},
            ],
            "rows": service_preview,
            "empty_state": "No connector or sales sync records are available yet.",
            "actions": [
                {"label": "Open sales", "url_name": "sales:list"},
                {"label": "Sync center", "url_name": "sales:sync_center"},
            ],
        },
        {
            "slug": "standards",
            "label": "Standards",
            "eyebrow": "Tasks and loss",
            "title": "Tasks and loss follow-up",
            "copy": "Use one board for overdue standards work and any live loss that still needs attention.",
            "stats": [
                {"label": "Overdue tasks", "value": overdue_task_count},
                {"label": "Due today", "value": tasks_due_today_count},
                {"label": "Breakages this week", "value": breakages_this_week},
            ],
            "rows": standards_preview,
            "empty_state": "No overdue tasks or fresh breakages need attention right now.",
            "actions": [
                {"label": "Open tasks", "url_name": "checklists:list"},
                {"label": "Review breakages", "url_name": "breakages:list"},
            ],
        },
    ]

    command_links = [
        {
            "label": "Approvals",
            "title": "Review draft requests",
            "copy": "Clear sign-off work before supplier cut-off gets missed.",
            "stat": f"{pending_order_count} waiting" if pending_order_count else "Queue clear",
            "href": _dashboard_href("orders:list", query="preset=drafts"),
        },
        {
            "label": "Deliveries",
            "title": "Track incoming stock",
            "copy": "Keep today's and tomorrow's deliveries visible until they land.",
            "stat": f"{deliveries_due_today} today · {deliveries_due_tomorrow} tomorrow",
            "href": _dashboard_href("orders:list", query="preset=pending"),
        },
        {
            "label": "Stock",
            "title": "Resolve low-stock pressure",
            "copy": "Jump straight to critical inventory lines before service slips.",
            "stat": f"{low_stock_count} low stock" if low_stock_count else "All lines stable",
            "href": _dashboard_href("stock:list", urgency="critical"),
        },
        {
            "label": "Standards",
            "title": "Clear overdue standards",
            "copy": "Use one board for checklist drift and live breakage follow-up.",
            "stat": f"{overdue_task_count} overdue" if overdue_task_count else "No overdue tasks",
            "href": _dashboard_href(
                "checklists:list",
                query="preset=overdue" if overdue_task_count else "status=pending",
            ),
        },
    ]

    focus_list = []
    next_draft = order_qs.filter(status=Order.Status.DRAFT).order_by("created_at").first()
    if next_draft:
        focus_list.append(
            {
                "task": f"Approve {next_draft.reference}",
                "owner": next_draft.created_by.username if next_draft.created_by else "Staff",
                "due": next_draft.created_at.astimezone(timezone.get_current_timezone()).strftime("%H:%M"),
                "state": "Pending",
                "href": _dashboard_href("orders:edit", args=[next_draft.pk]),
            }
        )

    overdue_task = checklist_qs.filter(completed=False, due_date__lt=today).order_by("due_date").first()
    if overdue_task:
        focus_list.append(
            {
                "task": overdue_task.title,
                "owner": overdue_task.assigned_to.username if overdue_task.assigned_to else "Unassigned",
                "due": overdue_task.due_date.strftime("%d %b"),
                "state": "Overdue",
                "href": _dashboard_href("checklists:edit", args=[overdue_task.pk]),
            }
        )

    due_delivery = order_qs.filter(
        delivery_date=today,
        status__in=[Order.Status.ORDERED, Order.Status.PENDING_DELIVERY],
    ).order_by("delivery_date", "created_at").first()
    if due_delivery:
        focus_list.append(
            {
                "task": f"Check {due_delivery.reference} delivery",
                "owner": due_delivery.supplier.name,
                "due": due_delivery.delivery_date.strftime("%d %b"),
                "state": "Scheduled",
                "href": _dashboard_href("orders:edit", args=[due_delivery.pk]),
            }
        )

    if not focus_list:
        focus_list.append(
            {
                "task": "No urgent operational blockers identified",
                "owner": "System",
                "due": "Today",
                "state": "Clear",
                "href": _dashboard_href("dashboard:management_portal"),
            }
        )

    attention_items = []
    if active_connector_count == 0:
        attention_items.append(
            {
                "label": "POS setup",
                "value": "No connectors",
                "copy": "Create the first live sales connector before relying on the premium sales layer.",
                "tone": "alert",
                "action_label": "Open sync center",
                "url_name": "sales:sync_center",
            }
        )
    elif connectors_needing_attention:
        attention_items.append(
            {
                "label": "Connector health",
                "value": f"{connectors_needing_attention} need review",
                "copy": "At least one feed is due, errored, or missing location mapping.",
                "tone": "warn",
                "action_label": "Review feeds",
                "url_name": "sales:sync_center",
            }
        )
    if latest_sales_snapshot is None or latest_sales_snapshot.business_date < today:
        attention_items.append(
            {
                "label": "Sales sync",
                "value": "Needs sync",
                "copy": "No synced daily sales snapshot has landed for today yet.",
                "tone": "alert",
                "action_label": "Log sales",
                "url_name": "sales:add",
            }
        )
    elif today_sales_snapshot and abs(today_sales_snapshot.payment_gap) >= 15:
        attention_items.append(
            {
                "label": "Payment gap",
                "value": f"£{abs(today_sales_snapshot.payment_gap):,.0f}",
                "copy": "Payment mix does not reconcile cleanly against today’s net sales.",
                "tone": "warn",
                "action_label": "Review sales",
                "url_name": "sales:list",
            }
        )
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
    if breakages_this_week:
        attention_items.append(
            {
                "label": "Breakage watch",
                "value": f"{breakages_this_week} this week",
                "copy": "Recurring loss patterns should still be reviewed before replacement orders go out.",
                "tone": "warn",
                "action_label": "Review breakages",
                "url_name": "breakages:list",
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
                "href": _dashboard_href("orders:edit", args=[order.pk]),
            }
        )

    for snapshot in sales_qs.order_by("-synced_at")[:5]:
        activity_events.append(
            {
                "moment": snapshot.synced_at,
                "category": "sales",
                "text": (
                    f"{snapshot.get_source_display()} sync captured "
                    f"£{snapshot.net_sales:,.0f} for {snapshot.business_date:%d %b}"
                ),
                "href": _dashboard_href("sales:list"),
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
                "href": _dashboard_href("shifts:edit", args=[shift.pk]),
            }
        )

    for task in checklist_qs.order_by("-updated_at")[:5]:
        status_label = "completed" if task.completed else "updated"
        activity_events.append(
            {
                "moment": task.updated_at,
                "category": "checklists",
                "text": f"Checklist task {status_label}: {task.title}",
                "href": _dashboard_href("checklists:edit", args=[task.pk]),
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
                "href": _dashboard_href("breakages:list", q=record.item_name),
            }
        )

    activity_events.sort(key=lambda item: item["moment"], reverse=True)
    activity = [
        {
            "time": _format_activity_time(item["moment"]),
            "text": item["text"],
            "category": item["category"],
            "href": item.get("href"),
        }
        for item in activity_events[:8]
    ]
    if not activity:
        activity = [
            {
                "time": "Now",
                "text": "No recent operational events recorded.",
                "category": "orders",
                "href": _dashboard_href("dashboard:management_portal"),
            }
        ]

    service_values = []
    for index, day in enumerate(last_seven_dates):
        service_values.append(
            order_qs.filter(created_at__date=day).count() + shift_qs.filter(shift_date=day).count()
        )

    metrics = [
        {
            **card,
            "actions": _normalize_link_items(card.get("actions", [])),
        }
        for card in metrics
    ]
    portal_sections = [
        {
            **section,
            "actions": _normalize_link_items(section.get("actions", [])),
            "module_href": _normalize_link_items(section.get("actions", []))[0]["href"]
            if section.get("actions")
            else "",
        }
        for section in portal_sections
    ]
    attention_items = _normalize_link_items(attention_items)

    return {
        "portal_title": "Management Portal",
        "overview_heading": "Management",
        "overview_copy": (
            f"{pending_order_count} approvals, "
            f"{connectors_needing_attention} sync issue(s), "
            f"{deliveries_due_today} delivery(ies) due today."
        ),
        "command_links": command_links,
        "metrics": metrics,
        "attention_items": attention_items,
        "activity": activity,
        "portal_sections": portal_sections,
        "focus_list": focus_list,
        "throughput": _build_throughput(
            last_seven_dates,
            service_values=service_values,
            task_values=task_output_series,
        ),
    }

def _staff_dashboard_payload(user, venue):
    today = timezone.localdate()

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    previous_week_start = week_start - timedelta(days=7)
    previous_week_end = week_start - timedelta(days=1)

    seven_day_start = today - timedelta(days=6)
    previous_seven_start = seven_day_start - timedelta(days=7)
    previous_seven_end = seven_day_start - timedelta(days=1)

    my_shifts_qs = Shift.objects.filter(
        venue=venue,
        staff=user,
    ).order_by(
        "shift_date",
        "start_time",
    )

    my_tasks_qs = Checklist.objects.filter(
        venue=venue,
        assigned_to=user,
    )
    my_orders_qs = Order.objects.filter(
        venue=venue,
        created_by=user,
    )
    my_breakages_qs = Breakage.objects.filter(
        venue=venue,
        reported_by=user,
    )
    stock_qs = StockItem.objects.filter(
        venue=venue,
        is_active=True,
    )

    hours_this_week = _sum_shift_hours(
        my_shifts_qs.filter(
            shift_date__range=(week_start, week_end),
        )
    )

    hours_last_week = _sum_shift_hours(
        my_shifts_qs.filter(
            shift_date__range=(previous_week_start, previous_week_end),
        )
    )

    next_shift = my_shifts_qs.filter(
        shift_date__gte=today,
    ).first()

    shifts_this_week_count = my_shifts_qs.filter(
        shift_date__range=(week_start, week_end),
    ).count()

    tasks_due_today = my_tasks_qs.filter(
        due_date=today,
        completed=False,
    ).count()

    tasks_overdue = my_tasks_qs.filter(
        due_date__lt=today,
        completed=False,
    ).count()

    open_task_count = my_tasks_qs.filter(
        completed=False,
    ).count()
    low_stock_count = stock_qs.filter(
        quantity__lte=F("minimum_level"),
    ).count()
    my_request_count = my_orders_qs.count()
    my_open_request_count = my_orders_qs.exclude(
        status__in=[Order.Status.DELIVERED, Order.Status.CANCELLED],
    ).count()
    my_breakages_this_week = my_breakages_qs.filter(
        created_at__date__gte=seven_day_start,
    ).count()

    completed_tasks_this_week = my_tasks_qs.filter(
        completed=True,
        completed_at__date__gte=seven_day_start,
    ).count()

    completed_tasks_last_week = my_tasks_qs.filter(
        completed=True,
        completed_at__date__range=(
            previous_seven_start,
            previous_seven_end,
        ),
    ).count()

    last_seven_dates = [
        seven_day_start + timedelta(days=offset)
        for offset in range(7)
    ]

    hours_series = []
    task_completion_series = []

    for day in last_seven_dates:
        hours_series.append(
            _sum_shift_hours(
                my_shifts_qs.filter(
                    shift_date=day,
                )
            )
        )

        task_completion_series.append(
            my_tasks_qs.filter(
                completed=True,
                completed_at__date=day,
            ).count()
        )

    if next_shift:
        next_shift_note = (
            f"Next shift: {next_shift.shift_date:%a %d %b}, "
            f"{next_shift.start_time:%H:%M}"
        )

        next_shift_short = (
            f"{next_shift.shift_date:%a %d %b} at "
            f"{next_shift.start_time:%H:%M}"
        )

        next_shift_value = (
            next_shift.start_time.strftime("%H:%M")
            if next_shift.shift_date == today
            else _format_short_date(next_shift.shift_date)
        )
    else:
        next_shift_note = "No upcoming shift scheduled."
        next_shift_short = "No shift booked"
        next_shift_value = "None"

    metrics = [
        {
            "label": "Next Shift",
            "value": next_shift_value,
            "tone": "ok" if next_shift else "warn",
            "state": "Booked" if next_shift else "Not scheduled",
            "state_tone": "ok" if next_shift else "warn",
            "summary": next_shift_note,
            "trend": {
                "label": "Your rota only",
                "direction": "flat",
            },
            "note": "Check your next start time before travelling in.",
            "chart_label": "7d rota hours",
            "chart_points": _build_chart_points(hours_series),
            "actions": [
                {
                    "label": "My rota",
                    "url_name": "shifts:list",
                },
            ],
        },
        {
            "label": "My Tasks",
            "value": open_task_count,
            "tone": "warn" if tasks_due_today or tasks_overdue else "ok",
            "state": (
                "Overdue"
                if tasks_overdue
                else "Due today"
                if tasks_due_today
                else "Clear"
            ),
            "state_tone": (
                "alert"
                if tasks_overdue
                else "warn"
                if tasks_due_today
                else "ok"
            ),
            "summary": (
                f"{tasks_overdue} overdue task(s) and "
                f"{tasks_due_today} due today."
                if tasks_due_today or tasks_overdue
                else "No urgent checklist tasks are assigned to you."
            ),
            "trend": _build_trend(
                completed_tasks_this_week,
                completed_tasks_last_week,
                "completed vs previous 7 days",
            ),
            "note": "Complete assigned tasks before handover.",
            "chart_label": "7d task output",
            "chart_points": _build_chart_points(task_completion_series),
            "actions": [
                {
                    "label": "Open tasks",
                    "url_name": "checklists:list",
                },
            ],
        },
        {
            "label": "Stock",
            "value": "View",
            "tone": "neutral",
            "state": "Available",
            "state_tone": "ok",
            "summary": "Check current stock levels before requesting anything.",
            "trend": {
                "label": "Live stock view",
                "direction": "flat",
            },
            "note": "Submit a stock request only when a line needs replenishment.",
            "chart_label": "Stock check",
            "chart_points": _build_chart_points([1, 1, 1, 1, 1, 1, 1]),
            "actions": [
                {
                    "label": "View stock",
                    "url_name": "stock:list",
                },
                {
                    "label": "Request stock",
                    "url_name": "orders:add",
                },
            ],
        },
        {
            "label": "Hours This Week",
            "value": f"{hours_this_week:.1f}",
            "tone": "neutral",
            "state": f"{shifts_this_week_count} shift(s)",
            "state_tone": "ok" if shifts_this_week_count else "warn",
            "summary": "Your own scheduled hours for this week.",
            "trend": _build_trend(
                round(hours_this_week),
                round(hours_last_week),
                "hours vs last week",
            ),
            "note": "Only your own rota is shown.",
            "chart_label": "7d rota load",
            "chart_points": _build_chart_points(hours_series),
            "actions": [
                {
                    "label": "My rota",
                    "url_name": "shifts:list",
                },
            ],
        },
    ]

    upcoming_shift_preview = [
        _shift_row(shift, today=today, management_view=False)
        for shift in my_shifts_qs.filter(
            shift_date__gte=today,
        )[:4]
    ]

    open_task_preview = [
        _task_row(task, today=today, management_view=False)
        for task in my_tasks_qs.filter(
            completed=False,
        ).order_by(
            "due_date",
            "created_at",
        )[:4]
    ]

    portal_sections = [
        {
            "slug": "tasks",
            "label": "My tasks",
            "eyebrow": "Today",
            "title": "Tasks assigned to you",
            "copy": "Clear your own checklist work before handover.",
            "stats": [
                {
                    "label": "Open tasks",
                    "value": open_task_count,
                },
                {
                    "label": "Due today",
                    "value": tasks_due_today,
                },
                {
                    "label": "Overdue",
                    "value": tasks_overdue,
                },
            ],
            "rows": open_task_preview,
            "empty_state": "No open checklist tasks are assigned to you right now.",
            "actions": [
                {
                    "label": "Open tasks",
                    "url_name": "checklists:list",
                },
            ],
        },
        {
            "slug": "stock",
            "label": "Stock",
            "eyebrow": "Cellar and bar",
            "title": "View stock availability",
            "copy": "Check what is low, then raise a request from the same workspace.",
            "stats": [
                {
                    "label": "Stock view",
                    "value": "Live",
                },
                {
                    "label": "Low lines",
                    "value": low_stock_count,
                },
                {
                    "label": "Request form",
                    "value": "Ready",
                },
            ],
            "rows": [],
            "empty_state": "Open the stock page to check current levels.",
            "actions": [
                {
                    "label": "View stock",
                    "url_name": "stock:list",
                },
                {
                    "label": "Request stock",
                    "url_name": "orders:add",
                },
            ],
        },
        {
            "slug": "rota",
            "label": "My rota",
            "eyebrow": "Schedule",
            "title": "Your upcoming shifts",
            "copy": "See your own upcoming shifts and this week's hours.",
            "stats": [
                {
                    "label": "Hours this week",
                    "value": f"{hours_this_week:.1f}h",
                },
                {
                    "label": "Shifts this week",
                    "value": shifts_this_week_count,
                },
                {
                    "label": "Next shift",
                    "value": next_shift_value,
                },
            ],
            "rows": upcoming_shift_preview,
            "empty_state": "No upcoming shifts are scheduled yet.",
            "actions": [
                {
                    "label": "Open rota",
                    "url_name": "shifts:list",
                },
            ],
        },
        {
            "slug": "handover",
            "label": "End of shift",
            "eyebrow": "Quick reports",
            "title": "Submit shift issues",
            "copy": "Use the handover forms for stock requests and incident reports.",
            "stats": [
                {
                    "label": "Open requests",
                    "value": my_open_request_count,
                },
                {
                    "label": "Reports 7d",
                    "value": my_breakages_this_week,
                },
                {
                    "label": "Total requests",
                    "value": my_request_count,
                },
            ],
            "rows": [],
            "empty_state": (
                "Use Request stock or Report breakage when something needs "
                "recording before handover."
            ),
            "actions": [
                {
                    "label": "Request stock",
                    "url_name": "orders:add",
                },
                {
                    "label": "Report breakage",
                    "url_name": "breakages:add",
                },
            ],
        },
    ]

    due_task = my_tasks_qs.filter(
        completed=False,
    ).order_by(
        "due_date",
        "created_at",
    ).first()

    focus_list = []

    if due_task:
        focus_list.append(
            {
                "task": due_task.title,
                "owner": "You",
                "due": due_task.due_date.strftime("%d %b"),
                "state": (
                    "Overdue"
                    if due_task.due_date < today
                    else "Due today"
                    if due_task.due_date == today
                    else "Open"
                ),
                "href": _dashboard_href("checklists:list", q=due_task.title, status="pending"),
            }
        )

    if next_shift:
        focus_list.append(
            {
                "task": "Check your next shift",
                "owner": "You",
                "due": (
                    f"{next_shift.shift_date:%d %b} "
                    f"{next_shift.start_time:%H:%M}"
                ),
                "state": "Scheduled",
                "href": _dashboard_href("shifts:list", query="range=upcoming"),
            }
        )

    if not focus_list:
        focus_list.append(
            {
                "task": "No immediate actions pending",
                "owner": "You",
                "due": "Today",
                "state": "Clear",
                "href": _dashboard_href("dashboard:staff_portal"),
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
                "action_label": "Open tasks",
                "url_name": "checklists:list",
                "query": "preset=overdue",
            }
        )

    if tasks_due_today:
        attention_items.append(
            {
                "label": "Due today",
                "value": f"{tasks_due_today} due",
                "copy": "These tasks should be finished before handover.",
                "tone": "warn",
                "action_label": "Open tasks",
                "url_name": "checklists:list",
                "query": "preset=today",
            }
        )

    if next_shift:
        attention_items.append(
            {
                "label": "Upcoming shift",
                "value": f"{next_shift.shift_date:%a %d %b}",
                "copy": (
                    f"Starts at {next_shift.start_time:%H:%M}. "
                    "Check your tasks before service gets busy."
                ),
                "tone": "neutral",
                "action_label": "My rota",
                "url_name": "shifts:list",
            }
        )

    if not attention_items:
        attention_items.append(
            {
                "label": "Today",
                "value": "Clear board",
                "copy": "No overdue tasks or immediate shift blockers are showing.",
                "tone": "ok",
                "action_label": "View stock",
                "url_name": "stock:list",
            }
        )

    quick_actions = [
        {
            "label": "Tasks",
            "title": "My tasks",
            "copy": "Open your assigned tasks.",
            "stat": (
                f"{tasks_overdue} overdue"
                if tasks_overdue
                else f"{tasks_due_today} due today"
                if tasks_due_today
                else "Queue clear"
            ),
            "url_name": "checklists:list",
            "query": (
                "preset=overdue"
                if tasks_overdue
                else "preset=today"
                if tasks_due_today
                else "status=pending"
            ),
            "action_label": "Open tasks",
            "href": _dashboard_href(
                "checklists:list",
                query=(
                    "preset=overdue"
                    if tasks_overdue
                    else "preset=today"
                    if tasks_due_today
                    else "status=pending"
                ),
            ),
        },
        {
            "label": "Stock",
            "title": "View stock",
            "copy": "Check current availability.",
            "stat": "Live stock view",
            "url_name": "stock:list",
            "action_label": "View stock",
            "href": _dashboard_href("stock:list"),
        },
        {
            "label": "Request",
            "title": "Request stock",
            "copy": "Raise a stock request.",
            "stat": f"{my_open_request_count} open" if my_open_request_count else "Form ready",
            "url_name": "orders:add",
            "action_label": "Request stock",
            "href": _dashboard_href("orders:add"),
        },
        {
            "label": "Breakage",
            "title": "Report breakage",
            "copy": "Log breakage or waste.",
            "stat": (
                f"{my_breakages_this_week} this week"
                if my_breakages_this_week
                else "Form ready"
            ),
            "url_name": "breakages:add",
            "action_label": "Report breakage",
            "href": _dashboard_href("breakages:add"),
        },
        {
            "label": "Rota",
            "title": "My rota",
            "copy": "Check your next shifts.",
            "stat": next_shift_short,
            "url_name": "shifts:list",
            "action_label": "Open rota",
            "href": _dashboard_href("shifts:list", query="range=upcoming"),
        },
    ]

    activity_events = []

    for shift in my_shifts_qs.order_by("-updated_at")[:5]:
        activity_events.append(
            {
                "moment": shift.updated_at,
                "category": "shifts",
                "text": (
                    f"Shift on {shift.shift_date:%d %b} "
                    f"({shift.start_time:%H:%M}-{shift.end_time:%H:%M})"
                ),
                "href": _dashboard_href("shifts:list", query="range=upcoming"),
            }
        )

    for task in my_tasks_qs.order_by("-updated_at")[:5]:
        task_state = "completed" if task.completed else "updated"

        activity_events.append(
            {
                "moment": task.updated_at,
                "category": "checklists",
                "text": f"Checklist task {task_state}: {task.title}",
                "href": _dashboard_href("checklists:list", q=task.title),
            }
        )

    activity_events.sort(
        key=lambda item: item["moment"],
        reverse=True,
    )

    activity = [
        {
            "time": _format_activity_time(item["moment"]),
            "text": item["text"],
            "category": item["category"],
            "href": item.get("href"),
        }
        for item in activity_events[:6]
    ]

    if not activity:
        activity = [
            {
                "time": "Now",
                "text": "No recent staff activity recorded.",
                "category": "shifts",
                "href": _dashboard_href("dashboard:staff_portal"),
            }
        ]

    service_values = []

    for day in last_seven_dates:
        service_values.append(
            _sum_shift_hours(
                my_shifts_qs.filter(
                    shift_date=day,
                )
            )
        )

    metrics = [
        {
            **card,
            "actions": _normalize_link_items(card.get("actions", [])),
        }
        for card in metrics
    ]
    portal_sections = [
        {
            **section,
            "actions": _normalize_link_items(section.get("actions", [])),
            "module_href": _normalize_link_items(section.get("actions", []))[0]["href"]
            if section.get("actions")
            else "",
        }
        for section in portal_sections
    ]
    attention_items = _normalize_link_items(attention_items)

    return {
        "portal_title": "Staff Portal",
        "overview_heading": "Today",
        "overview_copy": "Your shift, tasks, stock, and handover tools in one place.",
        "metrics": metrics,
        "attention_items": attention_items,
        "activity": activity,
        "portal_sections": portal_sections,
        "focus_list": focus_list,
        "quick_actions": quick_actions,
        "staff_snapshot": {
            "hours_this_week": f"{hours_this_week:.1f}",
            "tasks_due_today": tasks_due_today,
            "tasks_overdue": tasks_overdue,
            "next_shift_note": next_shift_note,
            "open_order_count": 0,
            "pending_delivery_count": 0,
            "breakages_this_week": 0,
        },
        "throughput": _build_throughput(
            last_seven_dates,
            service_values=service_values,
            task_values=task_completion_series,
        ),
    }

def _render_portal(request, *, management_view):
    venue = current_venue_or_404(request)
    payload = (
        _management_dashboard_payload(venue)
        if management_view
        else _staff_dashboard_payload(request.user, venue)
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


@active_venue_required
def home(request):
    return redirect(role_home_name(request.user, request=request))


@active_venue_required
def staff_portal(request):
    if is_management(request.user, request=request):
        return redirect("dashboard:management_portal")
    return _render_portal(request, management_view=False)


@management_required
def management_portal(request):
    return _render_portal(request, management_view=True)
