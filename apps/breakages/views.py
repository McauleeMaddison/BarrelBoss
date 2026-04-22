from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import management_required

from .forms import BreakageForm
from .models import Breakage


@login_required
def list_breakages(request):
    query = request.GET.get("q", "").strip()
    selected_issue = request.GET.get("issue", "")

    records_qs = Breakage.objects.select_related("reported_by")

    if query:
        records_qs = records_qs.filter(
            Q(item_name__icontains=query)
            | Q(notes__icontains=query)
            | Q(reported_by__username__icontains=query)
        )

    if selected_issue and selected_issue in Breakage.IssueType.values:
        records_qs = records_qs.filter(issue_type=selected_issue)

    records = list(records_qs)
    week_start = timezone.now() - timedelta(days=7)

    context = {
        "records": records,
        "record_count": len(records),
        "week_count": Breakage.objects.filter(created_at__gte=week_start).count(),
        "issue_choices": Breakage.IssueType.choices,
        "selected_issue": selected_issue,
        "query": query,
    }
    return render(request, "breakages/list.html", context)


@login_required
def add_breakage(request):
    if request.method == "POST":
        form = BreakageForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.reported_by = request.user
            record.save()
            messages.success(request, "Breakage incident logged.")
            return redirect("breakages:list")
    else:
        form = BreakageForm()

    return render(
        request,
        "breakages/form.html",
        {
            "form": form,
            "page_title": "Log Breakage Incident",
            "submit_label": "Log Incident",
        },
    )


@management_required
def delete_breakage(request, pk):
    record = get_object_or_404(Breakage, pk=pk)

    if request.method == "POST":
        record.delete()
        messages.success(request, "Breakage record deleted.")
        return redirect("breakages:list")

    return render(request, "breakages/confirm_delete.html", {"record": record})
