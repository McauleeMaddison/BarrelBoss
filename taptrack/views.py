import csv
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from apps.breakages.models import Breakage
from apps.checklists.models import Checklist
from apps.accounts.forms import StaffCreateForm, StaffUpdateForm
from apps.accounts.permissions import MANAGEMENT_ROLES, management_required, role_home_name
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from apps.accounts.push import (
    push_notifications_configured,
    unsubscribe_push_subscription,
    upsert_push_subscription,
)
from apps.orders.models import Order, OrderItem
from apps.accounts.models import StaffProfile
from apps.accounts.permissions import get_user_role, is_management
from apps.stock.models import StockItem
from taptrack.pagination import build_query_string, paginate_collection

User = get_user_model()


def _allowed_role_values_for_manager(editor_user):
    editor_role = get_user_role(editor_user)
    if editor_role == StaffProfile.Role.LANDLORD:
        return [choice[0] for choice in StaffProfile.Role.choices]
    return [StaffProfile.Role.MANAGER, StaffProfile.Role.STAFF]


def home_redirect(request):
    if request.user.is_authenticated:
        return redirect(role_home_name(request.user))
    return redirect("login")


@management_required
def staff_page(request):
    query = (request.GET.get("q") or "").strip()
    selected_status = request.GET.get("status", "all")
    selected_role = request.GET.get("role", "")
    selected_alerts = request.GET.get("alerts", "all")

    staff_qs = StaffProfile.objects.select_related("user").order_by("user__username")
    if query:
        staff_qs = staff_qs.filter(
            Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(phone__icontains=query)
            | Q(job_title__icontains=query)
        )

    if selected_status == "active":
        staff_qs = staff_qs.filter(is_active=True)
    elif selected_status == "inactive":
        staff_qs = staff_qs.filter(is_active=False)

    if selected_role in StaffProfile.Role.values:
        staff_qs = staff_qs.filter(role=selected_role)

    if selected_alerts == "enabled":
        staff_qs = staff_qs.filter(notify_on_shift_assignment=True)
    elif selected_alerts == "disabled":
        staff_qs = staff_qs.filter(notify_on_shift_assignment=False)

    staff_rows = list(staff_qs)
    role_badge_classes = {
        StaffProfile.Role.LANDLORD: "badge-role-landlord",
        StaffProfile.Role.MANAGER: "badge-role-manager",
        StaffProfile.Role.STAFF: "badge-role-staff",
    }
    role_sort_order = {
        StaffProfile.Role.LANDLORD: 0,
        StaffProfile.Role.MANAGER: 1,
        StaffProfile.Role.STAFF: 2,
    }

    for profile in staff_rows:
        full_name = profile.user.get_full_name().strip()
        display_name = full_name or profile.user.username
        if full_name:
            initials_source = full_name.split()
            initials = "".join(part[:1] for part in initials_source[:2]).upper()
        else:
            initials = profile.user.username[:2].upper()

        profile.display_name = display_name
        profile.initials = initials
        profile.role_badge_class = role_badge_classes.get(profile.role, "badge-role-staff")
        profile.status_badge_class = "stock-badge-ok" if profile.is_active else "stock-badge-low"
        profile.alert_badge_class = (
            "badge-alert-enabled" if profile.notify_on_shift_assignment else "badge-alert-disabled"
        )
        profile.alert_label = "Alerts On" if profile.notify_on_shift_assignment else "Alerts Off"

    staff_rows.sort(
        key=lambda profile: (
            not profile.is_active,
            role_sort_order.get(profile.role, 9),
            profile.user.username.lower(),
        )
    )

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="barrelboss-staff.csv"'
        writer = csv.writer(response)
        writer.writerow(["BarrelBoss Staff Export"])
        writer.writerow(
            [
                "Username",
                "Full Name",
                "Role",
                "Job Title",
                "Phone",
                "Email",
                "Status",
                "Shift Alerts",
                "Notes",
            ]
        )
        for profile in staff_rows:
            writer.writerow(
                [
                    profile.user.username,
                    profile.user.get_full_name(),
                    profile.get_role_display(),
                    profile.job_title,
                    profile.phone,
                    profile.user.email,
                    "Active" if profile.is_active else "Inactive",
                    "Enabled" if profile.notify_on_shift_assignment else "Disabled",
                    profile.notes,
                ]
            )
        return response

    page_obj = paginate_collection(request, staff_rows, per_page=12)
    display_rows = list(page_obj.object_list)

    team_active = sum(1 for item in staff_rows if item.is_active)
    team_shift_alerts_enabled = sum(
        1 for item in staff_rows if item.notify_on_shift_assignment
    )
    team_management = sum(1 for item in staff_rows if item.role in MANAGEMENT_ROLES)

    context = {
        "team_profiles": display_rows,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "filter_query": build_query_string(request, exclude_keys={"export"}),
        "query": query,
        "selected_status": selected_status,
        "selected_role": selected_role,
        "selected_alerts": selected_alerts,
        "status_choices": [
            ("all", "All"),
            ("active", "Active"),
            ("inactive", "Inactive"),
        ],
        "alert_choices": [
            ("all", "All"),
            ("enabled", "Alerts Enabled"),
            ("disabled", "Alerts Disabled"),
        ],
        "role_choices": StaffProfile.Role.choices,
        "team_total": len(staff_rows),
        "team_active": team_active,
        "team_inactive": len(staff_rows) - team_active,
        "team_management": team_management,
        "team_shift_alerts_enabled": team_shift_alerts_enabled,
        "team_shift_alerts_disabled": len(staff_rows) - team_shift_alerts_enabled,
    }
    return render(request, "accounts/staff.html", context)


@management_required
def add_staff_page(request):
    allowed_role_values = _allowed_role_values_for_manager(request.user)
    if request.method == "POST":
        form = StaffCreateForm(
            request.POST,
            allowed_role_values=allowed_role_values,
        )
        if form.is_valid():
            user = form.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=user.staff_profile,
                summary=f"Created staff account {user.username}",
                details={"role": user.staff_profile.role},
            )
            messages.success(request, f"Staff account '{user.username}' created.")
            return redirect("staff")
    else:
        form = StaffCreateForm(allowed_role_values=allowed_role_values)

    return render(
        request,
        "accounts/staff_form.html",
        {
            "form": form,
            "page_title": "Add Staff Member",
            "submit_label": "Create Staff Account",
        },
    )


@management_required
def edit_staff_page(request, user_id):
    staff_user = get_object_or_404(User.objects.select_related("staff_profile"), pk=user_id)
    profile = staff_user.staff_profile
    allowed_role_values = _allowed_role_values_for_manager(request.user)

    if (
        profile.role == StaffProfile.Role.LANDLORD
        and get_user_role(request.user) != StaffProfile.Role.LANDLORD
    ):
        messages.error(request, "Only landlord accounts can edit landlord profiles.")
        return redirect("staff")

    if request.method == "POST":
        form = StaffUpdateForm(
            request.POST,
            instance=profile,
            user_instance=staff_user,
            allowed_role_values=allowed_role_values,
        )
        if form.is_valid():
            if staff_user == request.user:
                if form.cleaned_data["role"] not in MANAGEMENT_ROLES:
                    form.add_error("role", "You cannot remove your own management access.")
                if not form.cleaned_data["is_active"]:
                    form.add_error("is_active", "You cannot deactivate your own account.")

            if not form.errors:
                form.save()
                record_audit_event(
                    request,
                    action=AuditEvent.Action.UPDATE,
                    target=profile,
                    summary=f"Updated staff profile for {staff_user.username}",
                    details={
                        "role": form.cleaned_data.get("role"),
                        "is_active": form.cleaned_data.get("is_active"),
                    },
                )
                messages.success(request, f"Updated staff profile for '{staff_user.username}'.")
                return redirect("staff")
    else:
        form = StaffUpdateForm(
            instance=profile,
            user_instance=staff_user,
            allowed_role_values=allowed_role_values,
        )

    return render(
        request,
        "accounts/staff_form.html",
        {
            "form": form,
            "page_title": f"Edit Staff Member: {staff_user.username}",
            "submit_label": "Save Changes",
            "staff_user": staff_user,
        },
    )


@management_required
@require_POST
def toggle_staff_active(request, user_id):
    staff_user = get_object_or_404(User.objects.select_related("staff_profile"), pk=user_id)
    profile = staff_user.staff_profile

    if staff_user == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("staff")

    profile.is_active = not profile.is_active
    profile.save(update_fields=["is_active", "updated_at"])
    record_audit_event(
        request,
        action=AuditEvent.Action.TOGGLE,
        target=profile,
        summary=f"Toggled active status for {staff_user.username}",
        details={"is_active": profile.is_active},
    )
    status_label = "active" if profile.is_active else "inactive"
    messages.success(request, f"{staff_user.username} is now marked as {status_label}.")
    return redirect("staff")


@management_required
def reports_page(request):
    range_days = request.GET.get("range", "7")
    if range_days not in {"7", "30", "90"}:
        range_days = "7"

    window_days = int(range_days)
    today = timezone.localdate()
    start_date = today - timedelta(days=window_days - 1)
    previous_end_date = start_date - timedelta(days=1)
    previous_start_date = previous_end_date - timedelta(days=window_days - 1)

    def _format_currency(value):
        return f"£{float(value or 0):,.2f}"

    def _build_delta(
        current_value,
        previous_value,
        *,
        positive_good=True,
        kind="count",
        precision=0,
    ):
        current_num = float(current_value or 0)
        previous_num = float(previous_value or 0)
        diff = current_num - previous_num
        if abs(diff) < 0.000001:
            return {
                "text": "No change vs previous period",
                "tone": "neutral",
            }

        improved = diff > 0 if positive_good else diff < 0
        tone = "up" if improved else "down"
        sign = "+" if diff > 0 else "-"
        magnitude = abs(diff)

        if kind == "currency":
            formatted = f"£{magnitude:,.2f}"
        elif kind == "percent":
            formatted = f"{magnitude:.1f}%"
        elif precision:
            formatted = f"{magnitude:.{precision}f}"
        else:
            formatted = f"{magnitude:,.0f}"

        return {
            "text": f"{sign}{formatted} vs previous period",
            "tone": tone,
        }

    cost_expression = ExpressionWrapper(
        F("quantity") * F("stock_item__cost"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    low_stock_rows = list(
        StockItem.objects.filter(
            is_active=True,
            quantity__lte=F("minimum_level"),
        )
        .select_related("supplier")
        .order_by("quantity", "name")
    )

    orders_window_qs = Order.objects.filter(order_date__range=(start_date, today))
    delivered_orders_qs = orders_window_qs.filter(status=Order.Status.DELIVERED)
    previous_orders_qs = Order.objects.filter(
        order_date__range=(previous_start_date, previous_end_date)
    )
    previous_delivered_orders_qs = previous_orders_qs.filter(status=Order.Status.DELIVERED)

    delivered_items_qs = OrderItem.objects.filter(order__in=delivered_orders_qs)
    previous_delivered_items_qs = OrderItem.objects.filter(order__in=previous_delivered_orders_qs)
    delivered_summary = delivered_items_qs.aggregate(
        total_units=Sum("quantity"),
        total_spend=Sum(cost_expression),
    )
    previous_delivered_summary = previous_delivered_items_qs.aggregate(
        total_units=Sum("quantity"),
        total_spend=Sum(cost_expression),
    )

    category_labels = dict(StockItem.Category.choices)
    category_volume_rows = []
    for row in (
        delivered_items_qs.values("stock_item__category")
        .annotate(
            total_units=Sum("quantity"),
            total_spend=Sum(cost_expression),
        )
        .order_by("-total_units")
    ):
        category_code = row["stock_item__category"]
        category_volume_rows.append(
            {
                "category_label": category_labels.get(category_code, category_code),
                "total_units": row["total_units"] or 0,
                "total_spend": row["total_spend"] or 0,
            }
        )

    supplier_spend_rows = list(
        delivered_items_qs.values("order__supplier__name")
        .annotate(
            total_units=Sum("quantity"),
            total_spend=Sum(cost_expression),
            total_lines=Count("id"),
        )
        .order_by("-total_spend", "-total_units")
    )

    breakages_window_qs = Breakage.objects.filter(created_at__date__range=(start_date, today))
    previous_breakages_qs = Breakage.objects.filter(
        created_at__date__range=(previous_start_date, previous_end_date)
    )
    breakage_totals = breakages_window_qs.aggregate(
        total_reports=Count("id"),
        total_units=Sum("quantity"),
    )
    previous_breakage_totals = previous_breakages_qs.aggregate(
        total_reports=Count("id"),
        total_units=Sum("quantity"),
    )
    issue_labels = dict(Breakage.IssueType.choices)
    breakage_issue_rows = []
    for row in (
        breakages_window_qs.values("issue_type")
        .annotate(total_reports=Count("id"), total_units=Sum("quantity"))
        .order_by("-total_units")
    ):
        issue_code = row["issue_type"]
        breakage_issue_rows.append(
            {
                "issue_label": issue_labels.get(issue_code, issue_code),
                "total_reports": row["total_reports"] or 0,
                "total_units": row["total_units"] or 0,
            }
        )

    top_breakage_items = list(
        breakages_window_qs.values("item_name")
        .annotate(total_units=Sum("quantity"), total_reports=Count("id"))
        .order_by("-total_units", "-total_reports", "item_name")[:8]
    )

    checklists_window_qs = Checklist.objects.filter(due_date__range=(start_date, today))
    previous_checklists_qs = Checklist.objects.filter(
        due_date__range=(previous_start_date, previous_end_date)
    )
    checklist_totals = checklists_window_qs.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(completed=True)),
    )
    previous_checklist_totals = previous_checklists_qs.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(completed=True)),
    )
    checklist_total = checklist_totals["total"] or 0
    checklist_completed = checklist_totals["completed"] or 0
    checklist_completion_rate = (
        round((checklist_completed / checklist_total) * 100, 1) if checklist_total else 0
    )
    previous_checklist_total = previous_checklist_totals["total"] or 0
    previous_checklist_completed = previous_checklist_totals["completed"] or 0
    previous_checklist_completion_rate = (
        round((previous_checklist_completed / previous_checklist_total) * 100, 1)
        if previous_checklist_total
        else 0
    )

    checklist_labels = dict(Checklist.ChecklistType.choices)
    checklist_type_rows = []
    for row in (
        checklists_window_qs.values("checklist_type")
        .annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(completed=True)),
        )
        .order_by("checklist_type")
    ):
        completed = row["completed"] or 0
        total = row["total"] or 0
        checklist_type_rows.append(
            {
                "type_label": checklist_labels.get(row["checklist_type"], row["checklist_type"]),
                "completed": completed,
                "total": total,
                "completion_rate": round((completed / total) * 100, 1) if total else 0,
            }
        )

    status_labels = dict(Order.Status.choices)
    order_status_rows = []
    orders_window_total = orders_window_qs.count()
    for row in orders_window_qs.values("status").annotate(total=Count("id")).order_by("status"):
        status_code = row["status"]
        status_total = row["total"] or 0
        order_status_rows.append(
            {
                "status_label": status_labels.get(status_code, status_code),
                "total": status_total,
                "percentage": round((status_total / orders_window_total) * 100, 1)
                if orders_window_total
                else 0,
            }
        )

    kpi_low_stock_count = len(low_stock_rows)
    kpi_delivered_orders = delivered_orders_qs.count()
    kpi_delivered_units = delivered_summary["total_units"] or 0
    kpi_supplier_spend = delivered_summary["total_spend"] or 0
    kpi_breakage_reports = breakage_totals["total_reports"] or 0
    kpi_breakage_units = breakage_totals["total_units"] or 0

    previous_delivered_orders = previous_delivered_orders_qs.count()
    previous_supplier_spend = previous_delivered_summary["total_spend"] or 0
    previous_breakage_reports = previous_breakage_totals["total_reports"] or 0
    delivered_orders_delta = _build_delta(
        kpi_delivered_orders,
        previous_delivered_orders,
        positive_good=True,
    )
    supplier_spend_delta = _build_delta(
        kpi_supplier_spend,
        previous_supplier_spend,
        positive_good=False,
        kind="currency",
    )
    breakage_reports_delta = _build_delta(
        kpi_breakage_reports,
        previous_breakage_reports,
        positive_good=False,
    )
    checklist_completion_delta = _build_delta(
        checklist_completion_rate,
        previous_checklist_completion_rate,
        positive_good=True,
        kind="percent",
    )

    critical_low_stock_count = sum(
        1
        for item in low_stock_rows
        if item.quantity == 0
        or (item.minimum_level > 0 and item.quantity <= (item.minimum_level / 2))
    )

    report_kpi_cards = [
        {
            "label": "Low Stock Items",
            "value": kpi_low_stock_count,
            "tone": "alert" if kpi_low_stock_count else "ok",
            "delta_text": (
                f"{critical_low_stock_count} critical item(s) need immediate restock"
                if kpi_low_stock_count
                else "Inventory currently above minimum thresholds"
            ),
            "delta_tone": "down" if kpi_low_stock_count else "up",
        },
        {
            "label": "Delivered Orders",
            "value": kpi_delivered_orders,
            "tone": "ok",
            "delta_text": delivered_orders_delta["text"],
            "delta_tone": delivered_orders_delta["tone"],
        },
        {
            "label": "Supplier Spend",
            "value": _format_currency(kpi_supplier_spend),
            "tone": "warn",
            "delta_text": supplier_spend_delta["text"],
            "delta_tone": supplier_spend_delta["tone"],
        },
        {
            "label": "Breakage Reports",
            "value": kpi_breakage_reports,
            "tone": "neutral",
            "delta_text": breakage_reports_delta["text"],
            "delta_tone": breakage_reports_delta["tone"],
        },
        {
            "label": "Checklist Completion",
            "value": f"{checklist_completion_rate}%",
            "tone": "ok" if checklist_completion_rate >= 80 else "warn",
            "delta_text": checklist_completion_delta["text"],
            "delta_tone": checklist_completion_delta["tone"],
        },
    ]

    backlog_order_count = Order.objects.filter(
        status__in=[
            Order.Status.DRAFT,
            Order.Status.ORDERED,
            Order.Status.PENDING_DELIVERY,
        ]
    ).count()

    top_supplier_row = supplier_spend_rows[0] if supplier_spend_rows else None
    top_category_row = category_volume_rows[0] if category_volume_rows else None
    weakest_checklist_row = (
        min(checklist_type_rows, key=lambda row: row["completion_rate"])
        if checklist_type_rows
        else None
    )
    dominant_breakage_issue = breakage_issue_rows[0] if breakage_issue_rows else None

    executive_highlights = [
        {
            "title": "Order Backlog",
            "value": backlog_order_count,
            "meta": "Draft, ordered, and pending delivery orders awaiting completion.",
            "tone": "warn" if backlog_order_count else "ok",
        },
        {
            "title": "Top Supplier by Spend",
            "value": top_supplier_row["order__supplier__name"] if top_supplier_row else "No data",
            "meta": (
                f"{_format_currency(top_supplier_row['total_spend'])} across "
                f"{top_supplier_row['total_units'] or 0} units"
                if top_supplier_row
                else "No delivered supplier spend in this window."
            ),
            "tone": "neutral",
        },
        {
            "title": "Highest Incoming Category",
            "value": top_category_row["category_label"] if top_category_row else "No data",
            "meta": (
                f"{top_category_row['total_units'] or 0} units delivered"
                if top_category_row
                else "No delivered stock volume in this window."
            ),
            "tone": "ok",
        },
        {
            "title": "Checklist Risk Area",
            "value": weakest_checklist_row["type_label"] if weakest_checklist_row else "No data",
            "meta": (
                f"{weakest_checklist_row['completion_rate']}% completion"
                if weakest_checklist_row
                else "No checklist activity in this window."
            ),
            "tone": "alert" if weakest_checklist_row and weakest_checklist_row["completion_rate"] < 70 else "neutral",
        },
        {
            "title": "Top Breakage Issue",
            "value": dominant_breakage_issue["issue_label"] if dominant_breakage_issue else "No data",
            "meta": (
                f"{dominant_breakage_issue['total_units']} units across "
                f"{dominant_breakage_issue['total_reports']} report(s)"
                if dominant_breakage_issue
                else "No breakages logged in this window."
            ),
            "tone": "warn" if dominant_breakage_issue else "ok",
        },
    ]

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="barrelboss-report-{today:%Y%m%d}-{window_days}d.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(["BarrelBoss Operational Report"])
        writer.writerow(["Window", f"{start_date:%d %b %Y} - {today:%d %b %Y}"])
        writer.writerow([])
        writer.writerow(["KPI", "Value"])
        writer.writerow(["Low Stock Items", kpi_low_stock_count])
        writer.writerow(["Delivered Orders", kpi_delivered_orders])
        writer.writerow(["Delivered Units", kpi_delivered_units])
        writer.writerow(["Supplier Spend", _format_currency(kpi_supplier_spend)])
        writer.writerow(["Breakage Reports", kpi_breakage_reports])
        writer.writerow(["Breakage Units", kpi_breakage_units])
        writer.writerow(["Checklist Completion", f"{checklist_completion_rate}%"])
        writer.writerow([])
        writer.writerow(["Low Stock Summary"])
        writer.writerow(["Item", "Category", "Quantity", "Minimum", "Supplier"])
        for item in low_stock_rows:
            writer.writerow(
                [
                    item.name,
                    item.get_category_display(),
                    f"{item.quantity} {item.get_unit_display()}",
                    item.minimum_level,
                    item.supplier.name if item.supplier else "-",
                ]
            )
        writer.writerow([])
        writer.writerow(["Supplier Spend"])
        writer.writerow(["Supplier", "Units", "Order Lines", "Estimated Spend"])
        for row in supplier_spend_rows:
            writer.writerow(
                [
                    row["order__supplier__name"],
                    row["total_units"] or 0,
                    row["total_lines"] or 0,
                    _format_currency(row["total_spend"] or 0),
                ]
            )
        return response

    context = {
        "selected_range": range_days,
        "range_choices": [
            ("7", "Last 7 days"),
            ("30", "Last 30 days"),
            ("90", "Last 90 days"),
        ],
        "report_window_label": f"{start_date:%d %b %Y} - {today:%d %b %Y}",
        "previous_window_label": f"{previous_start_date:%d %b %Y} - {previous_end_date:%d %b %Y}",
        "low_stock_rows": low_stock_rows,
        "category_volume_rows": category_volume_rows,
        "supplier_spend_rows": supplier_spend_rows,
        "breakage_issue_rows": breakage_issue_rows,
        "top_breakage_items": top_breakage_items,
        "checklist_type_rows": checklist_type_rows,
        "order_status_rows": order_status_rows,
        "kpi_low_stock_count": kpi_low_stock_count,
        "kpi_delivered_orders": kpi_delivered_orders,
        "kpi_delivered_units": kpi_delivered_units,
        "kpi_supplier_spend": kpi_supplier_spend,
        "kpi_breakage_reports": kpi_breakage_reports,
        "kpi_breakage_units": kpi_breakage_units,
        "kpi_checklist_completion_rate": checklist_completion_rate,
        "report_kpi_cards": report_kpi_cards,
        "executive_highlights": executive_highlights,
        "backlog_order_count": backlog_order_count,
    }
    return render(request, "reports/index.html", context)


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
                record_audit_event(
                    request,
                    action=AuditEvent.Action.SETTINGS,
                    summary="Updated team shift alert preferences",
                    details={"updated_count": updated_count},
                )
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
        record_audit_event(
            request,
            action=AuditEvent.Action.SETTINGS,
            summary="Enabled push notifications for current device",
            details={"endpoint": subscription.get("endpoint", "")[:120]},
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
    if deleted_count:
        record_audit_event(
            request,
            action=AuditEvent.Action.SETTINGS,
            summary="Disabled push notifications for current device",
            details={"deleted_count": deleted_count},
        )
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


def csrf_failure(request, reason=""):
    context = {"reason": reason}
    return render(request, "errors/403.html", context, status=403)


def error_403(request, exception=None):
    context = {"reason": str(exception) if exception else ""}
    return render(request, "errors/403.html", context, status=403)


def error_404(request, exception):
    context = {"path": request.path}
    return render(request, "errors/404.html", context, status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
