from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("management/", views.management_portal, name="management_portal"),
    path("staff/", views.staff_portal, name="staff_portal"),
]
