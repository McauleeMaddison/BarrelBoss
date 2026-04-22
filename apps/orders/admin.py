from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "supplier", "status", "order_date", "delivery_date", "created_by", "updated_at")
    list_filter = ("status", "supplier")
    search_fields = ("supplier__name", "notes", "created_by__username")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "stock_item", "quantity")
    list_filter = ("order__status",)
    search_fields = ("order__supplier__name", "stock_item__name")
