from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Breakage(models.Model):
    class IssueType(models.TextChoices):
        BROKEN = "BROKEN", "Broken"
        MISSING = "MISSING", "Missing"
        DAMAGED = "DAMAGED", "Damaged"
        REPLACEMENT_NEEDED = "REPLACEMENT_NEEDED", "Replacement Needed"

    item_name = models.CharField(max_length=150)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    issue_type = models.CharField(max_length=22, choices=IssueType.choices)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="breakages_reported",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["issue_type"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.item_name} ({self.get_issue_type_display()})"
