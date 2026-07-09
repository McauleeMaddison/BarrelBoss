from django.contrib import admin

from .models import Organisation, PushSubscription, StaffProfile, Venue, VenueInvite, VenueMembership


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


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "organisation", "slug", "is_active", "dashboard_focus")
    list_filter = ("is_active", "dashboard_focus", "organisation")
    search_fields = ("name", "slug", "organisation__name")


@admin.register(VenueMembership)
class VenueMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "venue", "role", "is_active", "is_default", "notify_on_shift_assignment")
    list_filter = ("role", "is_active", "is_default", "venue")
    search_fields = ("user__username", "user__email", "venue__name")


@admin.register(VenueInvite)
class VenueInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "venue", "role", "is_active", "expires_at", "accepted_at")
    list_filter = ("role", "is_active", "venue")
    search_fields = ("email", "venue__name", "token")
