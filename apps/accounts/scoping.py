from django.contrib.auth import get_user_model

from .models import VenueMembership


User = get_user_model()


def current_venue(request):
    return getattr(request, "active_venue", None)


def current_venue_or_404(request):
    venue = current_venue(request)
    if venue is None:
        raise ValueError("Request does not have an active venue.")
    return venue


def filter_for_active_venue(request, queryset, *, field_name="venue"):
    venue = current_venue(request)
    if venue is None:
        return queryset.none()
    return queryset.filter(**{field_name: venue})


def venue_memberships(request):
    venue = current_venue(request)
    if venue is None:
        return VenueMembership.objects.none()
    return VenueMembership.objects.select_related("user", "venue").filter(
        venue=venue,
        is_active=True,
    )


def venue_users(request):
    venue = current_venue(request)
    if venue is None:
        return User.objects.none()
    return User.objects.filter(
        venue_memberships__venue=venue,
        venue_memberships__is_active=True,
    ).distinct()


def membership_for_user_in_request_venue(request, user):
    venue = current_venue(request)
    if venue is None or not user or not user.is_authenticated:
        return None
    return (
        VenueMembership.objects.filter(
            venue=venue,
            user=user,
            is_active=True,
        )
        .select_related("venue", "venue__organisation")
        .first()
    )
