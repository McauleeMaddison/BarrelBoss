from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "actor_username",
        "actor_role",
        "action",
        "target_model",
        "target_id",
        "summary",
    )
    list_filter = ("action", "actor_role", "target_model", "created_at")
    search_fields = ("actor_username", "summary", "target_model", "target_id")
    readonly_fields = (
        "created_at",
        "actor",
        "actor_username",
        "actor_role",
        "action",
        "target_model",
        "target_id",
        "summary",
        "details",
        "request_path",
        "ip_address",
    )
