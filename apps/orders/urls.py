from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.list_orders, name="list"),
    path("add/", views.add_order, name="add"),
    path("<int:pk>/edit/", views.edit_order, name="edit"),
    path("<int:pk>/status/", views.update_order_status, name="status"),
]
