from django.conf import settings
from django.db import models


class Organisation(models.Model):
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Venue(models.Model):
    class DashboardFocus(models.TextChoices):
        OPERATIONS = "OPERATIONS", "Operations"
        TRADE = "TRADE", "Trade"
        SERVICE = "SERVICE", "Service"

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name="venues",
    )
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180)
    timezone = models.CharField(max_length=64, default="Europe/London")
    is_active = models.BooleanField(default=True)
    default_shift_start_time = models.TimeField(null=True, blank=True)
    default_shift_end_time = models.TimeField(null=True, blank=True)
    low_stock_buffer_percent = models.PositiveSmallIntegerField(default=50)
    dashboard_focus = models.CharField(
        max_length=16,
        choices=DashboardFocus.choices,
        default=DashboardFocus.OPERATIONS,
    )
    opening_handover_prompt = models.TextField(blank=True)
    closing_handover_prompt = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organisation__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "slug"],
                name="uniq_venue_org_slug",
            )
        ]

    def __str__(self):
        return f"{self.organisation.name} / {self.name}"


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        LANDLORD = "LANDLORD", "Landlord"
        MANAGER = "MANAGER", "Manager"
        STAFF = "STAFF", "Staff"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    phone = models.CharField(max_length=40, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    notify_on_shift_assignment = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class VenueMembership(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="venue_memberships",
    )
    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=StaffProfile.Role.choices,
        default=StaffProfile.Role.STAFF,
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    notify_on_shift_assignment = models.BooleanField(default=True)
    job_title = models.CharField(max_length=120, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="venue_memberships_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["venue__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "user"],
                name="uniq_venue_membership_user",
            )
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["venue", "role", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.venue.name} ({self.get_role_display()})"


class VenueInvite(models.Model):
    email = models.EmailField()
    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name="invites",
    )
    role = models.CharField(
        max_length=20,
        choices=StaffProfile.Role.choices,
        default=StaffProfile.Role.STAFF,
    )
    token = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    notify_on_shift_assignment = models.BooleanField(default=True)
    job_title = models.CharField(max_length=120, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="venue_invites_sent",
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_venue_invites",
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["venue", "is_active"]),
            models.Index(fields=["email", "is_active"]),
        ]

    def __str__(self):
        return f"{self.email} -> {self.venue.name}"


class PushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.username} push endpoint"

    @property
    def webpush_payload(self):
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh,
                "auth": self.auth,
            },
        }
