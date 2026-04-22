from django.urls import path

from . import views

app_name = "shifts"

urlpatterns = [
    path("", views.list_shifts, name="list"),
    path("add/", views.add_shift, name="add"),
    path("<int:pk>/edit/", views.edit_shift, name="edit"),
    path("<int:pk>/delete/", views.delete_shift, name="delete"),
]
