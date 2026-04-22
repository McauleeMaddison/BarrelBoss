from calendar import monthrange
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_management, management_required
from apps.accounts.push import send_shift_push_notification

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


@login_required
def list_shifts(request):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_end_day = monthrange(today.year, today.month)[1]
    month_start = today.replace(day=1)
    month_end = today.replace(day=month_end_day)

    selected_staff = request.GET.get("staff", "")
    selected_range = request.GET.get("range", "upcoming")

    visible_qs = Shift.objects.select_related("staff", "created_by")
    if not is_management(request.user):
        visible_qs = visible_qs.filter(staff=request.user)

    if is_management(request.user) and selected_staff.isdigit():
        visible_qs = visible_qs.filter(staff_id=int(selected_staff))

    shifts_qs = visible_qs
    if selected_range == "upcoming":
        shifts_qs = shifts_qs.filter(shift_date__gte=today)
    elif selected_range == "this_week":
        shifts_qs = shifts_qs.filter(shift_date__range=(week_start, week_end))
    elif selected_range == "past":
        shifts_qs = shifts_qs.filter(shift_date__lt=today)

    shifts = list(shifts_qs.order_by("shift_date", "start_time", "staff__username"))
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

    context = {
        "shifts": shifts,
        "selected_staff": selected_staff,
        "selected_range": selected_range,
        "range_choices": [
            ("upcoming", "Upcoming"),
            ("this_week", "This Week"),
            ("all", "All"),
            ("past", "Past"),
        ],
        "team_members": User.objects.filter(staff_profile__is_active=True).order_by("username"),
        "total_shifts": visible_qs.count(),
        "hours_this_week": _sum_hours(
            visible_qs.filter(shift_date__range=(week_start, week_end)).order_by("shift_date")
        ),
        "hours_this_month": _sum_hours(
            visible_qs.filter(shift_date__range=(month_start, month_end)).order_by("shift_date")
        ),
        "weekly_chart": weekly_chart,
        "peak_day": peak_day,
        "week_window_label": f"{week_start:%d %b} - {week_end:%d %b}",
        "upcoming_shift_count": visible_qs.filter(shift_date__gte=today).count(),
        "today": today,
        "next_shift": next_shift,
    }
    return render(request, "shifts/list.html", context)


@management_required
def add_shift(request):
    if request.method == "POST":
        form = ShiftForm(request.POST)
        if form.is_valid():
            shift = form.save(commit=False)
            shift.created_by = request.user
            shift.save()
            send_shift_push_notification(shift, actor=request.user, event_type="assigned")
            messages.success(request, "Shift scheduled successfully.")
            return redirect("shifts:list")
    else:
        form = ShiftForm()

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
    shift = get_object_or_404(Shift, pk=pk)

    if request.method == "POST":
        form = ShiftForm(request.POST, instance=shift)
        if form.is_valid():
            updated_shift = form.save()
            send_shift_push_notification(
                updated_shift,
                actor=request.user,
                event_type="updated",
            )
            messages.success(request, "Shift updated.")
            return redirect("shifts:list")
    else:
        form = ShiftForm(instance=shift)

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
    shift = get_object_or_404(Shift, pk=pk)

    if request.method == "POST":
        shift.delete()
        messages.success(request, "Shift deleted.")
        return redirect("shifts:list")

    return render(request, "shifts/confirm_delete.html", {"shift": shift})
