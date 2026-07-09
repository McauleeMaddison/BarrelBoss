from .models import StaffProfile, VenueMembership


ACTIVE_VENUE_SESSION_KEY = "barrelboss_active_venue_id"


def venue_memberships_for_user(user):
    if not user or not user.is_authenticated:
        return VenueMembership.objects.none()

    return (
        VenueMembership.objects.select_related("venue", "venue__organisation")
        .filter(
            user=user,
            is_active=True,
            venue__is_active=True,
            venue__organisation__is_active=True,
        )
        .order_by("-is_default", "venue__organisation__name", "venue__name")
    )


def resolve_active_membership(request):
    user = getattr(request, "user", None)
    memberships = venue_memberships_for_user(user)
    venue_id = request.session.get(ACTIVE_VENUE_SESSION_KEY)

    if venue_id:
        membership = memberships.filter(venue_id=venue_id).first()
        if membership:
            return membership

    membership = memberships.first()
    if membership:
        request.session[ACTIVE_VENUE_SESSION_KEY] = membership.venue_id
    return membership


def set_active_venue(request, venue):
    membership = venue_memberships_for_user(request.user).filter(venue=venue).first()
    if not membership:
        return None

    request.session[ACTIVE_VENUE_SESSION_KEY] = membership.venue_id
    request.active_membership = membership
    request.active_venue = membership.venue
    request.active_organisation = membership.venue.organisation
    return membership


def get_user_role(user, *, membership=None):
    if not user or not user.is_authenticated:
        return None

    if membership is not None:
        return membership.role

    if user.is_superuser:
        return StaffProfile.Role.LANDLORD

    profile = getattr(user, "staff_profile", None)
    if profile:
        return profile.role

    return StaffProfile.Role.STAFF


def user_has_active_venue(user):
    return venue_memberships_for_user(user).exists()
