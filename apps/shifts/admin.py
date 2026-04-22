from django.contrib import admin

from .models import Shift


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("staff", "shift_date", "start_time", "end_time", "break_minutes", "created_by")
    list_filter = ("shift_date", "staff")
    search_fields = ("staff__username", "staff__first_name", "staff__last_name", "notes")
    ordering = ("-shift_date", "start_time")
