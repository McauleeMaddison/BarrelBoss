from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def list_breakages(request):
    records = [
        {"item": "Pint Glass", "qty": 2, "issue": "Broken", "reported_by": "Nina Walsh", "date": "2026-04-21"},
        {"item": "Tray", "qty": 1, "issue": "Damaged", "reported_by": "Elliot Shaw", "date": "2026-04-20"},
    ]
    return render(request, "breakages/list.html", {"records": records})
