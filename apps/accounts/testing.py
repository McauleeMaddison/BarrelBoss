from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.text import slugify

from .models import Organisation, StaffProfile, Venue, VenueMembership


User = get_user_model()


def create_test_venue(*, organisation_name="BarrelBoss Test Group", venue_name="Main Bar"):
    organisation = Organisation.objects.create(
        name=organisation_name,
        slug=f"{slugify(organisation_name)}-{Organisation.objects.count() + 1}",
    )
    return Venue.objects.create(
        organisation=organisation,
        name=venue_name,
        slug=f"{slugify(venue_name)}-{Venue.objects.count() + 1}",
        low_stock_buffer_percent=50,
        dashboard_focus=Venue.DashboardFocus.OPERATIONS,
        opening_handover_prompt="Opening checks complete.",
        closing_handover_prompt="Closing checks complete.",
    )


def attach_user_to_venue(
    user,
    venue,
    *,
    role=StaffProfile.Role.STAFF,
    is_active=True,
    is_default=True,
    notify_on_shift_assignment=True,
    job_title="",
):
    profile = user.staff_profile
    profile.role = role
    if job_title:
        profile.job_title = job_title
    profile.is_active = is_active
    profile.notify_on_shift_assignment = notify_on_shift_assignment
    profile.save(
        update_fields=[
            "role",
            "job_title",
            "is_active",
            "notify_on_shift_assignment",
            "updated_at",
        ]
    )
    membership, _ = VenueMembership.objects.update_or_create(
        venue=venue,
        user=user,
        defaults={
            "role": role,
            "is_active": is_active,
            "is_default": is_default,
            "notify_on_shift_assignment": notify_on_shift_assignment,
            "job_title": job_title,
        },
    )
    return membership


class VenueScopedTestCase(TestCase):
    organisation_name = "BarrelBoss Test Group"
    venue_name = "Main Bar"

    def setUp(self):
        super().setUp()
        self.venue = create_test_venue(
            organisation_name=self.organisation_name,
            venue_name=self.venue_name,
        )

    def create_user(
        self,
        *,
        username,
        password="strong-pass-123",
        role=StaffProfile.Role.STAFF,
        is_active=True,
        is_default=True,
        notify_on_shift_assignment=True,
        job_title="",
        **kwargs,
    ):
        user = User.objects.create_user(username=username, password=password, **kwargs)
        attach_user_to_venue(
            user,
            self.venue,
            role=role,
            is_active=is_active,
            is_default=is_default,
            notify_on_shift_assignment=notify_on_shift_assignment,
            job_title=job_title,
        )
        return user

    def create_superuser_with_membership(
        self,
        *,
        username,
        email,
        password="strong-pass-123",
        role=StaffProfile.Role.LANDLORD,
        **kwargs,
    ):
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            **kwargs,
        )
        attach_user_to_venue(user, self.venue, role=role)
        return user
