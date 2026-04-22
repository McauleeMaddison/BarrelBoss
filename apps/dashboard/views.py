from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.accounts.permissions import is_management


@login_required
def home(request):
    management_view = is_management(request.user)

    if management_view:
        metrics = [
            {"label": "Low Stock Items", "value": 6, "tone": "alert"},
            {"label": "Barrel Orders Pending", "value": 2, "tone": "warn"},
            {"label": "Deliveries Due Today", "value": 1, "tone": "ok"},
            {"label": "Breakages This Week", "value": 4, "tone": "neutral"},
        ]
        activity = [
            "Opening checklist completed by Nina Walsh at 09:12",
            "Barrel order #1012 marked as pending delivery",
            "2 pint glasses logged as damaged",
        ]
    else:
        metrics = [
            {"label": "My Tasks Due Today", "value": 3, "tone": "warn"},
            {"label": "Deliveries to Confirm", "value": 1, "tone": "ok"},
            {"label": "Low Stock Reports Filed", "value": 2, "tone": "neutral"},
            {"label": "Breakages Logged", "value": 1, "tone": "alert"},
        ]
        activity = [
            "Your opening checklist is due by 10:00",
            "Delivery checklist assigned for ORD-1001",
            "Remember to log damaged glassware before handover",
        ]

    return render(
        request,
        "dashboard/home.html",
        {"metrics": metrics, "activity": activity, "management_view": management_view},
    )
