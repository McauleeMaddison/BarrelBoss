from django.urls import path

from . import views

app_name = "stock"

urlpatterns = [
    path("", views.list_items, name="list"),
]
