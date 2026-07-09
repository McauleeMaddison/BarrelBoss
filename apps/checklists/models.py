from django.conf import settings
from django.db import models


class Checklist(models.Model):
    class ChecklistType(models.TextChoices):
        OPENING = "OPENING", "Opening"
        CLOSING = "CLOSING", "Closing"
        DELIVERY = "DELIVERY", "Delivery"
        CLEANING = "CLEANING", "Cleaning"

    venue = models.ForeignKey(
        "accounts.Venue",
        on_delete=models.CASCADE,
        related_name="checklists",
        null=True,
        blank=True,
    )
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
            models.Index(fields=["venue", "checklist_type"]),
            models.Index(fields=["checklist_type"]),
            models.Index(fields=["completed"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_checklist_type_display()})"


class ChecklistTemplate(models.Model):
    venue = models.ForeignKey(
        "accounts.Venue",
        on_delete=models.CASCADE,
        related_name="checklist_templates",
    )
    title = models.CharField(max_length=180)
    checklist_type = models.CharField(max_length=20, choices=Checklist.ChecklistType.choices)
    notes = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["checklist_type", "sort_order", "title"]
        indexes = [
            models.Index(fields=["venue", "checklist_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.venue.name}: {self.title}"


class DailySignoff(models.Model):
    class SignoffType(models.TextChoices):
        OPENING = "OPENING", "Opening"
        CLOSING = "CLOSING", "Closing"

    venue = models.ForeignKey(
        "accounts.Venue",
        on_delete=models.CASCADE,
        related_name="daily_signoffs",
    )
    signoff_type = models.CharField(max_length=16, choices=SignoffType.choices)
    business_date = models.DateField()
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_signoffs_completed",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-business_date", "signoff_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "signoff_type", "business_date"],
                name="uniq_daily_signoff_per_venue_day",
            )
        ]
        indexes = [
            models.Index(fields=["venue", "business_date"]),
        ]

    def __str__(self):
        return f"{self.venue.name} {self.business_date} {self.get_signoff_type_display()}"
