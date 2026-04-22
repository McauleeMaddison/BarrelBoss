from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.permissions import is_management


def _greeting_line():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _management_dashboard_payload():
    return {
        "metrics": [
            {
                "label": "Low Stock Items",
                "value": 6,
                "tone": "alert",
                "delta": "+2 since yesterday",
                "note": "3 items are below emergency buffer",
            },
            {
                "label": "Barrel Orders Pending",
                "value": 2,
                "tone": "warn",
                "delta": "1 due tomorrow",
                "note": "Awaiting supplier confirmation",
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
            {"text": "Opening checklist completed by Nina Walsh", "time": "09:12", "category": "checklists"},
            {"text": "Barrel order #1012 marked as pending delivery", "time": "10:48", "category": "orders"},
            {"text": "2 pint glasses logged as damaged", "time": "11:35", "category": "breakages"},
        ],
        "quick_actions": [
            {
                "title": "Create Barrel Order",
                "url_name": "orders:add",
                "meta": "Add a draft order or mark delivery status.",
            },
            {
                "title": "Review Suppliers",
                "url_name": "suppliers:list",
                "meta": "Update contacts and preferred categories.",
            },
            {
                "title": "Check Stock Risks",
                "url_name": "stock:list",
                "meta": "Prioritise low stock lines before evening service.",
            },
        ],
        "focus_list": [
            {"task": "Approve Brewline order", "owner": "Morgan", "due": "13:00", "state": "Pending"},
            {"task": "Review weekend breakage trend", "owner": "Manager", "due": "16:30", "state": "Scheduled"},
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
        "metrics": [
            {
                "label": "My Tasks Due Today",
                "value": 3,
                "tone": "warn",
                "delta": "1 task overdue",
                "note": "Start with opening checklist items",
            },
            {
                "label": "Deliveries to Confirm",
                "value": 1,
                "tone": "ok",
                "delta": "Expected 15:30",
                "note": "Confirm quantity and condition",
            },
            {
                "label": "Low Stock Reports Filed",
                "value": 2,
                "tone": "neutral",
                "delta": "Submitted this shift",
                "note": "Awaiting manager review",
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
            {"text": "Your opening checklist is due by 10:00", "time": "09:00", "category": "checklists"},
            {"text": "Delivery checklist assigned for ORD-1001", "time": "11:10", "category": "orders"},
            {"text": "Remember to log damaged glassware before handover", "time": "11:45", "category": "breakages"},
        ],
        "quick_actions": [
            {
                "title": "Open Checklists",
                "url_name": "checklists:list",
                "meta": "Complete opening and closing tasks quickly.",
            },
            {
                "title": "Log Breakage",
                "url_name": "breakages:list",
                "meta": "Record broken or missing equipment.",
            },
            {
                "title": "View Current Stock",
                "url_name": "stock:list",
                "meta": "Spot low inventory and report it.",
            },
        ],
        "focus_list": [
            {"task": "Unlock stock room", "owner": "You", "due": "09:30", "state": "Pending"},
            {"task": "Restock back bar fridges", "owner": "You", "due": "11:00", "state": "In Progress"},
            {"task": "Confirm afternoon delivery", "owner": "You", "due": "15:30", "state": "Scheduled"},
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


@login_required
def home(request):
    management_view = is_management(request.user)
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
