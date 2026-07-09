from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .models import StaffProfile
from .tenancy import get_user_role as get_user_role_for_membership
from .tenancy import user_has_active_venue, venue_memberships_for_user


MANAGEMENT_ROLES = {StaffProfile.Role.LANDLORD, StaffProfile.Role.MANAGER}


def get_user_role(user, *, request=None):
    membership = getattr(request, "active_membership", None) if request is not None else None
    if membership is None and request is None and user and user.is_authenticated:
        membership = venue_memberships_for_user(user).first()
    return get_user_role_for_membership(user, membership=membership)


def is_management(user, *, request=None):
    return get_user_role(user, request=request) in MANAGEMENT_ROLES


def role_home_name(user, *, request=None):
    if is_management(user, request=request):
        return "dashboard:management_portal"
    return "dashboard:staff_portal"


def role_required(allowed_roles):
    allowed_role_labels = {
        StaffProfile.Role(role).label
        for role in allowed_roles
        if role in StaffProfile.Role.values
    }
    allowed_roles_text = ", ".join(sorted(allowed_role_labels)) if allowed_role_labels else "authorized"

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not getattr(request, "active_venue", None):
                if user_has_active_venue(request.user):
                    messages.error(request, "Select a venue before continuing.")
                else:
                    messages.info(request, "Create or join a venue before using BarrelBoss.")
                return redirect("venue_setup")

            if get_user_role(request.user, request=request) in allowed_roles:
                return view_func(request, *args, **kwargs)

            messages.error(
                request,
                f"Access denied. This page requires one of: {allowed_roles_text}.",
            )
            return redirect(role_home_name(request.user, request=request))

        return _wrapped

    return decorator


management_required = role_required(MANAGEMENT_ROLES)


def active_venue_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if getattr(request, "active_venue", None):
            return view_func(request, *args, **kwargs)

        if user_has_active_venue(request.user):
            messages.error(request, "Select a venue before continuing.")
        else:
            messages.info(request, "Create or join a venue before using BarrelBoss.")
        return redirect("venue_setup")

    return _wrapped
