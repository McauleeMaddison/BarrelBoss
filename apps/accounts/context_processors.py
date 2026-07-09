from .models import StaffProfile
from .permissions import get_user_role, is_management, role_home_name
from .tenancy import venue_memberships_for_user


def role_context(request):
    role = get_user_role(request.user, request=request)
    role_label = "Guest"

    if role:
        role_label = StaffProfile.Role(role).label

    memberships = []
    if getattr(request, "user", None) and request.user.is_authenticated:
        memberships = list(venue_memberships_for_user(request.user))

    return {
        "user_role": role,
        "user_role_label": role_label,
        "is_management": is_management(request.user, request=request),
        "role_home_url_name": role_home_name(request.user, request=request),
        "active_venue": getattr(request, "active_venue", None),
        "active_organisation": getattr(request, "active_organisation", None),
        "active_membership": getattr(request, "active_membership", None),
        "available_venue_memberships": memberships,
    }
