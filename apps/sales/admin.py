from django.contrib import admin

from .models import SalesSnapshot


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

