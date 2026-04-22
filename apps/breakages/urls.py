from django.urls import path

from . import views

app_name = "breakages"

urlpatterns = [
    path("", views.list_breakages, name="list"),
    path("add/", views.add_breakage, name="add"),
    path("<int:pk>/delete/", views.delete_breakage, name="delete"),
]
