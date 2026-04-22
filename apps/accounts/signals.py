from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import StaffProfile


@receiver(post_save, sender=get_user_model())
def ensure_staff_profile(sender, instance, created, **kwargs):
    defaults = {
        "role": StaffProfile.Role.LANDLORD if instance.is_superuser else StaffProfile.Role.STAFF
    }

    if created:
        StaffProfile.objects.create(user=instance, **defaults)
        return

    StaffProfile.objects.get_or_create(user=instance, defaults=defaults)
