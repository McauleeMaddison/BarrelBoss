from .models import StaffProfile
from .permissions import get_user_role, is_management, role_home_name


def role_context(request):
    role = get_user_role(request.user)
    role_label = "Guest"

    if role:
        role_label = StaffProfile.Role(role).label

    return {
        "user_role": role,
        "user_role_label": role_label,
        "is_management": is_management(request.user),
        "role_home_url_name": role_home_name(request.user),
    }
