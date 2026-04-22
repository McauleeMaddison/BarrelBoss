from django.urls import path

from . import views

app_name = "checklists"

urlpatterns = [
    path("", views.list_checklists, name="list"),
]
