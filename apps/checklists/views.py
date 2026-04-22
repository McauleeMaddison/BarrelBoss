from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_management, management_required

from .forms import ChecklistForm
from .models import Checklist


def _sync_completed_timestamp(task):
    if task.completed and not task.completed_at:
        task.completed_at = timezone.now()
    if not task.completed:
        task.completed_at = None


@login_required
def list_checklists(request):
    selected_type = request.GET.get("type", "")
    selected_status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()

    tasks_qs = Checklist.objects.select_related("assigned_to", "created_by")

    if not is_management(request.user):
        tasks_qs = tasks_qs.filter(assigned_to=request.user)

    if selected_type and selected_type in Checklist.ChecklistType.values:
        tasks_qs = tasks_qs.filter(checklist_type=selected_type)

    if selected_status == "pending":
        tasks_qs = tasks_qs.filter(completed=False)
    elif selected_status == "completed":
        tasks_qs = tasks_qs.filter(completed=True)

    if query:
        tasks_qs = tasks_qs.filter(
            Q(title__icontains=query)
            | Q(notes__icontains=query)
            | Q(assigned_to__username__icontains=query)
        )

    tasks = list(tasks_qs)
    today = timezone.localdate()
    week_ago = today - timedelta(days=7)

    visible_qs = Checklist.objects.select_related("assigned_to")
    if not is_management(request.user):
        visible_qs = visible_qs.filter(assigned_to=request.user)

    total = visible_qs.count()
    completed_count = visible_qs.filter(completed=True).count()
    completion_rate = int((completed_count / total) * 100) if total else 0

    context = {
        "tasks": tasks,
        "task_count": len(tasks),
        "due_today_count": visible_qs.filter(due_date=today, completed=False).count(),
        "overdue_count": visible_qs.filter(due_date__lt=today, completed=False).count(),
        "completed_week_count": visible_qs.filter(
            completed=True,
            completed_at__date__gte=week_ago,
        ).count(),
        "completion_rate": completion_rate,
        "type_choices": Checklist.ChecklistType.choices,
        "selected_type": selected_type,
        "selected_status": selected_status,
        "query": query,
        "status_choices": [
            ("pending", "Pending"),
            ("completed", "Completed"),
        ],
    }
    return render(request, "checklists/list.html", context)


@management_required
def add_checklist(request):
    if request.method == "POST":
        form = ChecklistForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            _sync_completed_timestamp(task)
            task.save()
            messages.success(request, "Checklist task assigned.")
            return redirect("checklists:list")
    else:
        form = ChecklistForm()

    return render(
        request,
        "checklists/form.html",
        {
            "form": form,
            "page_title": "Assign Checklist Task",
            "submit_label": "Assign Task",
        },
    )


@management_required
def edit_checklist(request, pk):
    task = get_object_or_404(Checklist, pk=pk)

    if request.method == "POST":
        form = ChecklistForm(request.POST, instance=task)
        if form.is_valid():
            task = form.save(commit=False)
            _sync_completed_timestamp(task)
            task.save()
            messages.success(request, "Checklist task updated.")
            return redirect("checklists:list")
    else:
        form = ChecklistForm(instance=task)

    return render(
        request,
        "checklists/form.html",
        {
            "form": form,
            "page_title": f"Edit {task.title}",
            "submit_label": "Save Changes",
            "task": task,
        },
    )


@login_required
def toggle_complete(request, pk):
    task = get_object_or_404(Checklist, pk=pk)

    if not is_management(request.user) and task.assigned_to_id != request.user.id:
        messages.error(request, "You can only update tasks assigned to you.")
        return redirect("checklists:list")

    if request.method == "POST":
        task.completed = not task.completed
        _sync_completed_timestamp(task)
        task.save(update_fields=["completed", "completed_at", "updated_at"])
        messages.success(request, "Checklist status updated.")

    return redirect("checklists:list")


@management_required
def delete_checklist(request, pk):
    task = get_object_or_404(Checklist, pk=pk)

    if request.method == "POST":
        task.delete()
        messages.success(request, "Checklist task deleted.")
        return redirect("checklists:list")

    return render(request, "checklists/confirm_delete.html", {"task": task})
