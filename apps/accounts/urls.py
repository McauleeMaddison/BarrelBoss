from django.urls import path

from . import views


urlpatterns = [
    path("venues/setup/", views.venue_setup, name="venue_setup"),
    path("venues/switch/<int:venue_id>/", views.switch_venue, name="switch_venue"),
    path("venues/invites/", views.venue_invites, name="venue_invites"),
    path("venues/invites/<str:token>/", views.accept_venue_invite, name="accept_venue_invite"),
]
