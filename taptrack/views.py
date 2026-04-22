from django.shortcuts import redirect, render

from apps.accounts.permissions import management_required, role_home_name


def home_redirect(request):
    if request.user.is_authenticated:
        return redirect(role_home_name(request.user))
    return redirect("login")


@management_required
def staff_page(request):
    team = [
        {"name": "Morgan Doyle", "role": "Manager", "status": "Active"},
        {"name": "Nina Walsh", "role": "Bartender", "status": "Active"},
        {"name": "Elliot Shaw", "role": "Barback", "status": "Inactive"},
    ]
    return render(request, "accounts/staff.html", {"team": team})


@management_required
def reports_page(request):
    report_tiles = [
        "Low Stock Summary",
        "Weekly Usage",
        "Supplier Spend",
        "Breakage Trends",
    ]
    return render(request, "reports/index.html", {"report_tiles": report_tiles})


@management_required
def settings_page(request):
    return render(request, "settings/index.html")
