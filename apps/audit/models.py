from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        STATUS = "STATUS", "Status Update"
        TOGGLE = "TOGGLE", "Toggle"
        SETTINGS = "SETTINGS", "Settings"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_username = models.CharField(max_length=150, blank=True)
    actor_role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=16, choices=Action.choices)
    target_model = models.CharField(max_length=120, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    request_path = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["target_model", "created_at"]),
            models.Index(fields=["actor_username", "created_at"]),
        ]

    def __str__(self):
        actor = self.actor_username or "system"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {actor} {self.action} {self.summary}"
