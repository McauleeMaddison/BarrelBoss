from django.conf import settings
from django.db import models


class Checklist(models.Model):
    class ChecklistType(models.TextChoices):
        OPENING = "OPENING", "Opening"
        CLOSING = "CLOSING", "Closing"
        DELIVERY = "DELIVERY", "Delivery"
        CLEANING = "CLEANING", "Cleaning"

    title = models.CharField(max_length=180)
    checklist_type = models.CharField(max_length=20, choices=ChecklistType.choices)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklist_tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checklists_created",
    )
    due_date = models.DateField()
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["completed", "due_date", "created_at"]
        indexes = [
            models.Index(fields=["checklist_type"]),
            models.Index(fields=["completed"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_checklist_type_display()})"
