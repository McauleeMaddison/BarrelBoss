from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .models import StaffProfile


MANAGEMENT_ROLES = {StaffProfile.Role.LANDLORD, StaffProfile.Role.MANAGER}


def get_user_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return StaffProfile.Role.LANDLORD

    profile = getattr(user, "staff_profile", None)
    if profile:
        return profile.role

    return StaffProfile.Role.STAFF


def is_management(user):
    return get_user_role(user) in MANAGEMENT_ROLES


def role_home_name(user):
    if is_management(user):
        return "dashboard:home"
    return "checklists:list"


def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if get_user_role(request.user) in allowed_roles:
                return view_func(request, *args, **kwargs)

            messages.error(request, "You do not have access to that page.")
            return redirect(role_home_name(request.user))

        return _wrapped

    return decorator


management_required = role_required(MANAGEMENT_ROLES)
