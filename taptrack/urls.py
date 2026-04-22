from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.accounts.views import RoleLoginView

from . import views as core_views

urlpatterns = [
    path("", core_views.home_redirect, name="home"),
    path("service-worker.js", core_views.service_worker, name="service_worker"),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        RoleLoginView.as_view(),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("dashboard/", include("apps.dashboard.urls")),
    path("stock/", include("apps.stock.urls")),
    path("orders/", include("apps.orders.urls")),
    path("suppliers/", include("apps.suppliers.urls")),
    path("breakages/", include("apps.breakages.urls")),
    path("checklists/", include("apps.checklists.urls")),
    path("shifts/", include("apps.shifts.urls")),
    path("staff/", core_views.staff_page, name="staff"),
    path("reports/", core_views.reports_page, name="reports"),
    path("settings/", core_views.settings_page, name="settings"),
    path("settings/push/subscribe/", core_views.push_subscribe, name="push_subscribe"),
    path(
        "settings/push/unsubscribe/",
        core_views.push_unsubscribe,
        name="push_unsubscribe",
    ),
]
