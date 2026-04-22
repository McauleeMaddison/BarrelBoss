from calendar import monthrange
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_management, management_required

from .forms import ShiftForm
from .models import Shift


def _sum_hours(shifts_qs):
    return round(sum(shift.duration_hours for shift in shifts_qs), 2)


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
            form.save()
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
