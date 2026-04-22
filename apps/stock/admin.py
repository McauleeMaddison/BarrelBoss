from django.contrib import admin

from .models import StockItem


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "quantity",
        "minimum_level",
        "unit",
        "supplier",
        "is_active",
        "updated_at",
    )
    list_filter = ("category", "unit", "is_active")
    search_fields = ("name", "notes", "supplier__name")
