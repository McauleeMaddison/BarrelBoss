from types import MethodType

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.accounts.views import PublicPasswordResetView, RoleLoginView

from . import views as core_views


def _admin_superuser_only(self, request):
    user = getattr(request, "user", None)
    return bool(user and user.is_active and user.is_superuser)


admin.site.has_permission = MethodType(_admin_superuser_only, admin.site)

urlpatterns = [
    path("", core_views.home_redirect, name="home"),
    path("service-worker.js", core_views.service_worker, name="service_worker"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path(
        "accounts/login/",
        RoleLoginView.as_view(),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/password-reset/",
        PublicPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("dashboard/", include("apps.dashboard.urls")),
    path("stock/", include("apps.stock.urls")),
    path("orders/", include("apps.orders.urls")),
    path("suppliers/", include("apps.suppliers.urls")),
    path("breakages/", include("apps.breakages.urls")),
    path("checklists/", include("apps.checklists.urls")),
    path("shifts/", include("apps.shifts.urls")),
    path("sales/", include("apps.sales.urls")),
    path("audit/", include("apps.audit.urls")),
    path("staff/", core_views.staff_page, name="staff"),
    path("staff/add/", core_views.add_staff_page, name="staff_add"),
    path("staff/<int:user_id>/edit/", core_views.edit_staff_page, name="staff_edit"),
    path(
        "staff/<int:user_id>/toggle-active/",
        core_views.toggle_staff_active,
        name="staff_toggle_active",
    ),
    path("reports/", core_views.reports_page, name="reports"),
    path("settings/", core_views.settings_page, name="settings"),
    path("settings/push/subscribe/", core_views.push_subscribe, name="push_subscribe"),
    path(
        "settings/push/unsubscribe/",
        core_views.push_unsubscribe,
        name="push_unsubscribe",
    ),
]

handler403 = "taptrack.views.error_403"
handler404 = "taptrack.views.error_404"
handler500 = "taptrack.views.error_500"
