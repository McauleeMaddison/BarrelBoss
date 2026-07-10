from django.urls import path

from . import views


urlpatterns = [
    path("venue/setup/", views.venue_setup, name="venue_setup"),
    path("venue/<int:venue_id>/switch/", views.switch_venue, name="switch_venue"),
    path("venue/invites/", views.venue_invites, name="venue_invites"),
    path("invite/<str:token>/", views.accept_venue_invite, name="accept_venue_invite"),
]
