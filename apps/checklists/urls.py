from django.urls import path

from . import views

app_name = "checklists"

urlpatterns = [
    path("", views.list_checklists, name="list"),
    path("add/", views.add_checklist, name="add"),
    path("<int:pk>/edit/", views.edit_checklist, name="edit"),
    path("<int:pk>/toggle/", views.toggle_complete, name="toggle"),
    path("<int:pk>/delete/", views.delete_checklist, name="delete"),
]
