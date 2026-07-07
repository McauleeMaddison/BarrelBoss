from django.contrib import admin

from .models import PosIntegration, PosLocationMapping, PosSyncRun, PosWebhookEvent, SalesSnapshot


@admin.register(SalesSnapshot)
class SalesSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "business_date",
        "location_name",
        "source",
        "sync_mode",
        "net_sales",
        "transactions",
        "covers",
        "uploaded_by",
    )
    list_filter = ("source", "sync_mode", "business_date", "location_name")
    search_fields = ("location_name", "external_reference", "notes")
    ordering = ("-business_date", "-synced_at", "-id")


@admin.register(PosIntegration)
class PosIntegrationAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "provider",
        "is_enabled",
        "auto_sync_enabled",
        "webhook_enabled",
        "last_success_at",
        "last_error_at",
    )
    list_filter = ("provider", "is_enabled", "auto_sync_enabled", "webhook_enabled")
    search_fields = ("label", "account_identifier", "notes")
    ordering = ("label",)


@admin.register(PosLocationMapping)
class PosLocationMappingAdmin(admin.ModelAdmin):
    list_display = (
        "integration",
        "external_location_name",
        "internal_location_name",
        "is_primary",
        "is_active",
        "auto_import_enabled",
        "latest_business_date",
    )
    list_filter = ("integration__provider", "is_active", "auto_import_enabled", "is_primary")
    search_fields = (
        "integration__label",
        "external_location_name",
        "external_location_id",
        "internal_location_name",
    )


@admin.register(PosSyncRun)
class PosSyncRunAdmin(admin.ModelAdmin):
    list_display = (
        "integration",
        "business_date",
        "trigger_type",
        "status",
        "snapshots_imported",
        "imported_net_sales",
        "started_at",
    )
    list_filter = ("trigger_type", "status", "integration__provider")
    search_fields = ("integration__label", "payload_summary", "error_message")
    ordering = ("-started_at",)


@admin.register(PosWebhookEvent)
class PosWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "integration",
        "event_type",
        "external_event_id",
        "status",
        "received_at",
        "processed_at",
    )
    list_filter = ("status", "integration__provider")
    search_fields = ("integration__label", "event_type", "external_event_id", "notes")
    ordering = ("-received_at",)
