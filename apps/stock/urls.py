from django.urls import path

from . import views

app_name = "stock"

urlpatterns = [
    path("", views.list_items, name="list"),
    path("add/", views.add_item, name="add"),
    path("<int:pk>/counted/", views.mark_counted, name="mark_counted"),
    path("<int:pk>/edit/", views.edit_item, name="edit"),
    path("<int:pk>/delete/", views.delete_item, name="delete"),
]
