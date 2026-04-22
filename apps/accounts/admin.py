from django.contrib import admin

from .models import PushSubscription, StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "job_title",
        "phone",
        "is_active",
        "notify_on_shift_assignment",
        "updated_at",
    )
    list_filter = ("role", "is_active", "notify_on_shift_assignment")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "phone",
        "job_title",
    )


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "is_active", "updated_at", "created_at")
    list_filter = ("is_active", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "endpoint")
