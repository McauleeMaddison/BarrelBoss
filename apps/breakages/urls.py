from django.urls import path

from . import views

app_name = "breakages"

urlpatterns = [
    path("", views.list_breakages, name="list"),
]
