from django.contrib import admin

from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_name", "phone", "email", "category_supplied", "updated_at")
    list_filter = ("category_supplied",)
    search_fields = ("name", "contact_name", "email", "phone")
