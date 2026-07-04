from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("", views.list_sales, name="list"),
    path("add/", views.add_sales_snapshot, name="add"),
    path("<int:pk>/edit/", views.edit_sales_snapshot, name="edit"),
]

