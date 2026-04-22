from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def list_checklists(request):
    tasks = [
        {"title": "Unlock stock room", "type": "Opening", "assignee": "Nina Walsh", "status": "Complete"},
        {"title": "Restock bar fridges", "type": "Opening", "assignee": "Elliot Shaw", "status": "Pending"},
        {"title": "Log breakages", "type": "Closing", "assignee": "Morgan Doyle", "status": "Pending"},
    ]
    return render(request, "checklists/list.html", {"tasks": tasks})
