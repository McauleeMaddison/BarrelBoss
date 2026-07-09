from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import StaffProfile, Venue, VenueMembership


@receiver(post_save, sender=get_user_model())
def ensure_staff_profile(sender, instance, created, **kwargs):
    defaults = {
        "role": StaffProfile.Role.LANDLORD if instance.is_superuser else StaffProfile.Role.STAFF
    }

    if created:
        profile = StaffProfile.objects.create(user=instance, **defaults)
        _attach_default_membership(instance, profile)
        return

    profile, _ = StaffProfile.objects.get_or_create(user=instance, defaults=defaults)
    _attach_default_membership(instance, profile)


def _attach_default_membership(user, profile):
    if VenueMembership.objects.filter(user=user).exists():
        return

    active_venues = list(Venue.objects.filter(is_active=True).order_by("id")[:2])
    if len(active_venues) != 1:
        return

    VenueMembership.objects.create(
        venue=active_venues[0],
        user=user,
        role=profile.role,
        is_active=profile.is_active,
        is_default=True,
        notify_on_shift_assignment=profile.notify_on_shift_assignment,
        job_title=profile.job_title,
    )
