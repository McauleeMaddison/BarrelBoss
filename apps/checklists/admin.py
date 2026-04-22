from django.contrib import admin

from .models import Checklist


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "checklist_type",
        "assigned_to",
        "due_date",
        "completed",
        "completed_at",
    )
    list_filter = ("checklist_type", "completed", "due_date")
    search_fields = ("title", "notes", "assigned_to__username", "created_by__username")
