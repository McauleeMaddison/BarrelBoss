from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_management, management_required, role_home_name


def _greeting_line():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _management_dashboard_payload():
    return {
        "portal_title": "Management Portal",
        "overview_heading": "Management Overview",
        "overview_copy": "Approve orders, oversee team hours, and keep service operations on track.",
        "metrics": [
            {
                "label": "Order Requests Awaiting Approval",
                "value": 5,
                "tone": "alert",
                "delta": "+2 since yesterday",
                "note": "Review staff requests before supplier cut-off",
            },
            {
                "label": "Shifts Requiring Update",
                "value": 3,
                "tone": "warn",
                "delta": "2 end-time edits pending",
                "note": "Confirm worked hours before payroll export",
            },
            {
                "label": "Deliveries Due Today",
                "value": 1,
                "tone": "ok",
                "delta": "ETA 15:30",
                "note": "Brewline driver assigned",
            },
            {
                "label": "Breakages This Week",
                "value": 4,
                "tone": "neutral",
                "delta": "-1 vs last week",
                "note": "Mostly glassware incidents",
            },
        ],
        "activity": [
            {"text": "Staff order request ORD-1012 submitted for approval", "time": "09:12", "category": "orders"},
            {"text": "Shift for Nina Walsh updated to 23:30 finish", "time": "10:48", "category": "shifts"},
            {"text": "2 pint glasses logged as damaged", "time": "11:35", "category": "breakages"},
        ],
        "quick_actions": [
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
        ],
        "focus_list": [
            {"task": "Approve Brewline order request", "owner": "Morgan", "due": "13:00", "state": "Pending"},
            {"task": "Confirm updated staff shift hours", "owner": "Manager", "due": "16:30", "state": "Scheduled"},
            {"task": "Assign closing checklist lead", "owner": "Landlord", "due": "18:00", "state": "Open"},
        ],
        "throughput": [
            {"label": "Mon", "value": 62, "task_value": 34},
            {"label": "Tue", "value": 74, "task_value": 42},
            {"label": "Wed", "value": 68, "task_value": 55},
            {"label": "Thu", "value": 82, "task_value": 67},
            {"label": "Fri", "value": 95, "task_value": 79},
            {"label": "Sat", "value": 100, "task_value": 88},
            {"label": "Sun", "value": 71, "task_value": 48},
        ],
    }


def _staff_dashboard_payload():
    return {
        "portal_title": "Staff Portal",
        "overview_heading": "Staff Shift Overview",
        "overview_copy": "Check your shift hours and submit stock order requests for management approval.",
        "metrics": [
            {
                "label": "Hours This Week",
                "value": "31.5",
                "tone": "ok",
                "delta": "2 shifts left",
                "note": "Based on your scheduled shifts",
            },
            {
                "label": "Order Requests Submitted",
                "value": 3,
                "tone": "warn",
                "delta": "1 awaiting manager review",
                "note": "Open orders can be edited while in draft",
            },
            {
                "label": "My Tasks Due Today",
                "value": 2,
                "tone": "neutral",
                "delta": "No overdue tasks",
                "note": "Complete checklists before handover",
            },
            {
                "label": "Breakages Logged",
                "value": 1,
                "tone": "alert",
                "delta": "No unresolved incidents",
                "note": "Report any new damage immediately",
            },
        ],
        "activity": [
            {"text": "Your next shift starts at 17:00", "time": "09:00", "category": "shifts"},
            {"text": "Order request ORD-1008 moved to pending delivery", "time": "11:10", "category": "orders"},
            {"text": "Remember to log damaged glassware before handover", "time": "11:45", "category": "breakages"},
        ],
        "quick_actions": [
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
        ],
        "focus_list": [
            {"task": "Review tonight's shift schedule", "owner": "You", "due": "15:00", "state": "Pending"},
            {"task": "Submit beer reorder request", "owner": "You", "due": "16:00", "state": "In Progress"},
            {"task": "Complete closing checklist", "owner": "You", "due": "22:30", "state": "Scheduled"},
        ],
        "throughput": [
            {"label": "10:00", "value": 28, "task_value": 20},
            {"label": "12:00", "value": 41, "task_value": 32},
            {"label": "14:00", "value": 36, "task_value": 27},
            {"label": "16:00", "value": 58, "task_value": 39},
            {"label": "18:00", "value": 73, "task_value": 52},
            {"label": "20:00", "value": 81, "task_value": 61},
        ],
    }


def _render_portal(request, *, management_view):
    payload = _management_dashboard_payload() if management_view else _staff_dashboard_payload()
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
