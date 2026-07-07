from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("", views.list_sales, name="list"),
    path("sync/", views.sync_center, name="sync_center"),
    path("sync/run-due/", views.run_due_syncs, name="run_due_syncs"),
    path("sync/integrations/add/", views.add_pos_integration, name="integration_add"),
    path(
        "sync/integrations/<int:pk>/edit/",
        views.edit_pos_integration,
        name="integration_edit",
    ),
    path(
        "sync/integrations/<int:pk>/run/",
        views.run_integration_sync,
        name="integration_run",
    ),
    path("sync/mappings/add/", views.add_pos_location_mapping, name="mapping_add"),
    path("webhooks/<int:pk>/receive/", views.receive_pos_webhook, name="webhook"),
    path("add/", views.add_sales_snapshot, name="add"),
    path("<int:pk>/edit/", views.edit_sales_snapshot, name="edit"),
]
