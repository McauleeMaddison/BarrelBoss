from calendar import monthrange
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.scoping import current_venue_or_404, venue_users
from apps.accounts.permissions import active_venue_required, is_management, management_required
from apps.accounts.push import send_shift_push_notification
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from taptrack.module_ui import build_module_link, build_module_panel, build_module_snapshot
from taptrack.pagination import build_query_string, paginate_collection

from .forms import ShiftForm
from .models import Shift


def _sum_hours(shifts_qs):
    return round(sum(shift.duration_hours for shift in shifts_qs), 2)


def _hours_label(hours):
    whole_hours = int(hours)
    minutes = int(round((hours - whole_hours) * 60))
    if minutes == 60:
        whole_hours += 1
        minutes = 0

    if whole_hours and minutes:
        return f"{whole_hours}h {minutes:02d}m"
    if whole_hours:
        return f"{whole_hours}h"
    if minutes:
        return f"{minutes}m"
    return "0h"


@active_venue_required
def list_shifts(request):
    venue = current_venue_or_404(request)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_end_day = monthrange(today.year, today.month)[1]
    month_start = today.replace(day=1)
    month_end = today.replace(day=month_end_day)

    selected_staff = request.GET.get("staff", "")
    selected_range = request.GET.get("range", "upcoming")
    range_choices = [
        ("upcoming", "Upcoming"),
        ("this_week", "This Week"),
        ("all", "All"),
        ("past", "Past"),
    ]

    management_view = is_management(request.user, request=request)
    visible_qs = Shift.objects.select_related("staff", "created_by").filter(venue=venue)
    if not management_view:
        visible_qs = visible_qs.filter(staff=request.user)

    if management_view and selected_staff.isdigit():
        visible_qs = visible_qs.filter(staff_id=int(selected_staff))

    shifts_qs = visible_qs
    if selected_range == "upcoming":
        shifts_qs = shifts_qs.filter(shift_date__gte=today)
    elif selected_range == "this_week":
        shifts_qs = shifts_qs.filter(shift_date__range=(week_start, week_end))
    elif selected_range == "past":
        shifts_qs = shifts_qs.filter(shift_date__lt=today)

    ordered_shifts_qs = shifts_qs.order_by("shift_date", "start_time", "staff__username")
    page_obj = paginate_collection(request, ordered_shifts_qs, per_page=12)
    shifts = list(page_obj.object_list)
    week_shifts = list(
        visible_qs.filter(shift_date__range=(week_start, week_end)).order_by(
            "shift_date",
            "start_time",
        )
    )
    weekly_hours_totals = {week_start + timedelta(days=index): 0.0 for index in range(7)}
    for shift in week_shifts:
        weekly_hours_totals[shift.shift_date] += shift.duration_hours

    max_weekly_hours = max(weekly_hours_totals.values(), default=0.0)
    weekly_chart = []
    for chart_date, chart_hours in weekly_hours_totals.items():
        scaled_height = 0
        if max_weekly_hours > 0:
            scaled_height = int(round((chart_hours / max_weekly_hours) * 100))
            if chart_hours > 0 and scaled_height < 8:
                scaled_height = 8

        weekly_chart.append(
            {
                "label": chart_date.strftime("%a"),
                "full_date": chart_date.strftime("%A %d %b"),
                "hours": round(chart_hours, 2),
                "pretty_hours": _hours_label(chart_hours),
                "height": scaled_height,
            }
        )

    peak_day = max(weekly_chart, key=lambda point: point["hours"]) if weekly_chart else None

    next_shift = (
        visible_qs.filter(shift_date__gte=today)
        .order_by("shift_date", "start_time")
        .first()
    )
    priority_shifts = list(ordered_shifts_qs[:5])
    total_shifts = visible_qs.count()
    hours_this_week = _sum_hours(
        visible_qs.filter(shift_date__range=(week_start, week_end)).order_by("shift_date")
    )
    hours_this_month = _sum_hours(
        visible_qs.filter(shift_date__range=(month_start, month_end)).order_by("shift_date")
    )
    upcoming_shift_count = visible_qs.filter(shift_date__gte=today).count()
    days_with_cover = sum(1 for point in weekly_chart if point["hours"] > 0)

    if management_view and upcoming_shift_count == 0:
        primary_title = "Schedule the next shift"
        primary_copy = (
            "No upcoming coverage is showing, so the rota should be extended before service planning goes stale."
        )
        primary_url = reverse("shifts:add")
        primary_label = "Schedule shift"
    elif selected_range != "upcoming":
        primary_title = "Return to upcoming coverage"
        primary_copy = (
            "Use the live upcoming queue as the main working view, then widen the range only when you need history."
        )
        primary_url = f"{reverse('shifts:list')}?range=upcoming"
        primary_label = "Open upcoming shifts"
    elif management_view:
        primary_title = "Keep the rota moving"
        primary_copy = (
            "Stay inside one clean schedule board, then adjust people and hours only where coverage actually needs it."
        )
        primary_url = reverse("shifts:add")
        primary_label = "Schedule shift"
    else:
        primary_title = "Review your next shifts"
        primary_copy = (
            "Stay focused on your upcoming service windows and only open wider history when you need to check worked hours."
        )
        primary_url = f"{reverse('shifts:list')}?range=upcoming"
        primary_label = "Open upcoming shifts"

    module_panel = build_module_panel(
        hero_class="shifts-hero",
        kicker="Rota Management" if management_view else "My Rota",
        badge="Team Planner" if management_view else "Schedule View",
        title=(
            "Keep coverage, hours, and the next live shift easy to scan."
            if management_view
            else "See your next shifts and this week's hours without digging through the rota."
        ),
        copy=(
            "Use one rota board for immediate coverage, weekly load, and the full shift list so the team is not bouncing between duplicate views."
            if management_view
            else "Use one clean schedule board for your next shifts, weekly hours, and the full rota without extra clutter."
        ),
        primary_title=primary_title,
        primary_copy=primary_copy,
        primary_url=primary_url,
        primary_label=primary_label,
        utility_links=[
            *([build_module_link("Schedule shift", reverse("shifts:add"))] if management_view else []),
            build_module_link("This week", f"{reverse('shifts:list')}?range=this_week"),
            build_module_link("All shifts", f"{reverse('shifts:list')}?range=all"),
        ],
        toolbar_notes=[
            week_start.strftime("%d %b") + " - " + week_end.strftime("%d %b"),
            f"{upcoming_shift_count} upcoming",
            f"{total_shifts} visible",
        ],
    )
    module_snapshots = [
        build_module_snapshot(
            label="Hours this week",
            state="Current week",
            tone="ok",
            value=f"{hours_this_week:.2f}h",
            copy="Scheduled hours inside the current Monday to Sunday operating window.",
            action_label="Open week",
            action_url=f"{reverse('shifts:list')}?range=this_week",
        ),
        build_module_snapshot(
            label="Hours this month",
            state="Monthly load",
            tone="neutral",
            value=f"{hours_this_month:.2f}h",
            copy="Booked hours across the current calendar month in the visible rota scope.",
            action_label="Open all shifts",
            action_url=f"{reverse('shifts:list')}?range=all",
        ),
        build_module_snapshot(
            label="Upcoming shifts",
            state="Forward view" if upcoming_shift_count else "Clear",
            tone="warn" if upcoming_shift_count else "ok",
            value=upcoming_shift_count,
            copy="Future shifts from today onward, which is the fastest read on remaining rota pressure.",
            action_label="Open upcoming",
            action_url=f"{reverse('shifts:list')}?range=upcoming",
        ),
        build_module_snapshot(
            label="Days with cover",
            state=peak_day["label"] if peak_day else "No peak",
            tone="neutral",
            value=days_with_cover,
            copy=(
                f"Peak day {peak_day['full_date']} at {peak_day['pretty_hours']}."
                if peak_day
                else "No scheduled hours are showing in the current week window."
            ),
            action_label="View week load",
            action_url=f"{reverse('shifts:list')}?range=this_week",
        ),
    ]

    context = {
        "shifts": shifts,
        "priority_shifts": priority_shifts,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "selected_staff": selected_staff,
        "selected_range": selected_range,
        "range_choices": range_choices,
        "team_members": venue_users(request).order_by("username"),
        "total_shifts": total_shifts,
        "hours_this_week": hours_this_week,
        "hours_this_month": hours_this_month,
        "weekly_chart": weekly_chart,
        "peak_day": peak_day,
        "week_window_label": f"{week_start:%d %b} - {week_end:%d %b}",
        "upcoming_shift_count": upcoming_shift_count,
        "today": today,
        "next_shift": next_shift,
        "days_with_cover": days_with_cover,
        "filters_active": bool(
            (management_view and selected_staff)
            or selected_range != "upcoming"
        ),
        "active_filter_count": sum(
            [
                bool(selected_staff) if management_view else 0,
                selected_range != "upcoming",
            ]
        ),
        "selected_staff_label": (
            venue_users(request).filter(pk=int(selected_staff)).values_list("username", flat=True).first()
            if selected_staff.isdigit()
            else ""
        ),
        "selected_range_label": dict(range_choices).get(selected_range, "Upcoming")
        if selected_range != "upcoming"
        else "",
        "filter_presets": [
            {
                "label": "Upcoming",
                "query": "range=upcoming",
                "active": selected_range == "upcoming" and not selected_staff,
            },
            {
                "label": "This Week",
                "query": "range=this_week",
                "active": selected_range == "this_week" and not selected_staff,
            },
            {
                "label": "All Shifts",
                "query": "range=all",
                "active": selected_range == "all" and not selected_staff,
            },
            {
                "label": "Past",
                "query": "range=past",
                "active": selected_range == "past" and not selected_staff,
            },
        ],
    }
    context["selected_preset_label"] = next(
        (
            preset["label"]
            for preset in context["filter_presets"]
            if preset["active"] and preset["query"] != "range=upcoming"
        ),
        "",
    )
    attention_items = []
    if context["upcoming_shift_count"] == 0:
        attention_items.append(
            {
                "label": "Upcoming coverage",
                "value": "No future shifts",
                "copy": "Nothing is currently scheduled ahead, which may be intentional or may need rota review.",
                "tone": "warn",
                "action_label": "Open planner",
                "url_name": "shifts:list",
                "query": "range=all",
            }
        )
    if context["hours_this_week"] == 0:
        attention_items.append(
            {
                "label": "This week",
                "value": "0h booked",
                "copy": "The current week has no scheduled hours in the selected staff or range scope.",
                "tone": "alert",
                "action_label": "View week",
                "url_name": "shifts:list",
                "query": "range=this_week",
            }
        )
    if next_shift:
        attention_items.append(
            {
                "label": "Next shift",
                "value": next_shift.shift_date.strftime("%a %d %b"),
                "copy": f"Starts at {next_shift.start_time.strftime('%H:%M')} and remains the next active service window in view.",
                "tone": "ok",
                "action_label": "Open upcoming",
                "url_name": "shifts:list",
                "query": "range=upcoming",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Shift board",
                "value": "Balanced",
                "copy": "No immediate rota gaps are showing in the selected view.",
                "tone": "ok",
                "action_label": "Open shifts",
                "url_name": "shifts:list",
            }
        )
    context["attention_items"] = attention_items
    context["module_panel"] = module_panel
    context["module_snapshots"] = module_snapshots
    return render(request, "shifts/list.html", context)


@management_required
def add_shift(request):
    venue = current_venue_or_404(request)
    if request.method == "POST":
        form = ShiftForm(request.POST, venue=venue)
        if form.is_valid():
            shift = form.save(commit=False)
            shift.venue = venue
            shift.created_by = request.user
            shift.save()
            send_shift_push_notification(shift, actor=request.user, event_type="assigned")
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=shift,
                summary=f"Scheduled shift for {shift.staff.username}",
                details={
                    "shift_date": str(shift.shift_date),
                    "start_time": shift.start_time.strftime("%H:%M"),
                    "end_time": shift.end_time.strftime("%H:%M"),
                },
            )
            messages.success(request, "Shift scheduled successfully.")
            return redirect("shifts:list")
    else:
        form = ShiftForm(venue=venue)

    return render(
        request,
        "shifts/form.html",
        {
            "form": form,
            "page_title": "Schedule Shift",
            "submit_label": "Schedule Shift",
        },
    )


@management_required
def edit_shift(request, pk):
    venue = current_venue_or_404(request)
    shift = get_object_or_404(Shift, pk=pk, venue=venue)

    if request.method == "POST":
        form = ShiftForm(request.POST, instance=shift, venue=venue)
        if form.is_valid():
            updated_shift = form.save()
            send_shift_push_notification(
                updated_shift,
                actor=request.user,
                event_type="updated",
            )
            record_audit_event(
                request,
                action=AuditEvent.Action.UPDATE,
                target=updated_shift,
                summary=f"Updated shift for {updated_shift.staff.username}",
                details={
                    "shift_date": str(updated_shift.shift_date),
                    "start_time": updated_shift.start_time.strftime("%H:%M"),
                    "end_time": updated_shift.end_time.strftime("%H:%M"),
                },
            )
            messages.success(request, "Shift updated.")
            return redirect("shifts:list")
    else:
        form = ShiftForm(instance=shift, venue=venue)

    return render(
        request,
        "shifts/form.html",
        {
            "form": form,
            "page_title": f"Edit Shift for {shift.staff.username}",
            "submit_label": "Save Changes",
            "shift": shift,
        },
    )


@management_required
def delete_shift(request, pk):
    shift = get_object_or_404(Shift, pk=pk, venue=current_venue_or_404(request))

    if request.method == "POST":
        record_audit_event(
            request,
            action=AuditEvent.Action.DELETE,
            target=shift,
            summary=f"Deleted shift for {shift.staff.username}",
            details={"shift_date": str(shift.shift_date)},
        )
        shift.delete()
        messages.success(request, "Shift deleted.")
        return redirect("shifts:list")

    return render(request, "shifts/confirm_delete.html", {"shift": shift})
