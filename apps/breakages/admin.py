from django.contrib import admin

from .models import Breakage


@admin.register(Breakage)
class BreakageAdmin(admin.ModelAdmin):
    list_display = ("item_name", "quantity", "issue_type", "reported_by", "created_at")
    list_filter = ("issue_type", "created_at")
    search_fields = ("item_name", "notes", "reported_by__username")
