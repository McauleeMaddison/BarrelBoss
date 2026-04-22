from django.urls import path

from . import views

app_name = "suppliers"

urlpatterns = [
    path("", views.list_suppliers, name="list"),
    path("add/", views.add_supplier, name="add"),
    path("<int:pk>/edit/", views.edit_supplier, name="edit"),
    path("<int:pk>/delete/", views.delete_supplier, name="delete"),
]
