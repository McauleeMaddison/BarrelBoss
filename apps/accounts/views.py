from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event

from .forms import VenueInviteAcceptForm, VenueInviteForm, VenueSetupForm
from .permissions import is_management, role_home_name
from .tenancy import set_active_venue, user_has_active_venue, venue_memberships_for_user
from .models import VenueInvite


class RoleLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        if not user_has_active_venue(self.request.user):
            return self.get_redirect_url() or reverse("venue_setup")
        return self.get_redirect_url() or reverse(
            role_home_name(self.request.user, request=self.request)
        )


@login_required
def venue_setup(request):
    if user_has_active_venue(request.user) and not is_management(request.user, request=request):
        messages.error(request, "Only management can create additional venues.")
        return redirect(role_home_name(request.user, request=request))

    if request.method == "POST":
        form = VenueSetupForm(request.POST)
        if form.is_valid():
            venue = form.save(
                user=request.user,
                organisation=getattr(request, "active_organisation", None),
            )
            set_active_venue(request, venue)
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=venue,
                summary=f"Created venue {venue.name}",
                details={"organisation": venue.organisation.name},
            )
            messages.success(request, f"{venue.name} is ready for onboarding.")
            return redirect("dashboard:management_portal")
    else:
        form = VenueSetupForm(
            initial={
                "organisation_name": (
                    request.active_organisation.name
                    if getattr(request, "active_organisation", None)
                    else ""
                )
            }
        )

    return render(
        request,
        "accounts/venue_setup.html",
        {
            "form": form,
            "page_title": "Set Up Organisation and Venue",
            "submit_label": "Create Venue",
        },
    )


@login_required
def switch_venue(request, venue_id):
    membership = venue_memberships_for_user(request.user).filter(venue_id=venue_id).first()
    if membership is None:
        messages.error(request, "You do not have access to that venue.")
        return redirect("venue_setup")

    set_active_venue(request, membership.venue)
    messages.success(request, f"Switched to {membership.venue.name}.")
    return redirect(role_home_name(request.user, request=request))


@login_required
def venue_invites(request):
    if not getattr(request, "active_venue", None):
        return redirect("venue_setup")
    if not is_management(request.user, request=request):
        messages.error(request, "Only management can create venue invites.")
        return redirect(role_home_name(request.user, request=request))
    if request.method == "POST":
        form = VenueInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(venue=request.active_venue, invited_by=request.user)
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=invite,
                summary=f"Created invite for {invite.email}",
                details={"role": invite.role},
            )
            messages.success(request, f"Invite created for {invite.email}.")
            return redirect("venue_invites")
    else:
        form = VenueInviteForm()

    invites = (
        request.active_venue.invites.select_related("invited_by", "accepted_by")
        .order_by("-created_at")
    )
    return render(
        request,
        "accounts/venue_invites.html",
        {
            "form": form,
            "invites": invites,
            "now": timezone.now(),
        },
    )


def accept_venue_invite(request, token):
    invite = get_object_or_404(VenueInvite.objects.select_related("venue", "venue__organisation"), token=token)
    if not invite.is_active or invite.expires_at <= timezone.now():
        messages.error(request, "This invite link is no longer active.")
        return redirect("login")

    if request.user.is_authenticated:
        from .models import VenueMembership

        if request.user.email and request.user.email.lower() != invite.email.lower():
            messages.error(request, "This invite belongs to a different email address.")
            return redirect(role_home_name(request.user, request=request))

        VenueMembership.objects.update_or_create(
            venue=invite.venue,
            user=request.user,
            defaults={
                "role": invite.role,
                "job_title": invite.job_title,
                "notify_on_shift_assignment": invite.notify_on_shift_assignment,
                "is_active": True,
                "is_default": True,
                "invited_by": invite.invited_by,
            },
        )
        profile = request.user.staff_profile
        profile.role = invite.role
        profile.job_title = invite.job_title
        profile.notify_on_shift_assignment = invite.notify_on_shift_assignment
        profile.is_active = True
        profile.save(
            update_fields=[
                "role",
                "job_title",
                "notify_on_shift_assignment",
                "is_active",
                "updated_at",
            ]
        )
        invite.accepted_by = request.user
        invite.accepted_at = timezone.now()
        invite.is_active = False
        invite.save(update_fields=["accepted_by", "accepted_at", "is_active", "updated_at"])
        set_active_venue(request, invite.venue)
        messages.success(request, f"You now have access to {invite.venue.name}.")
        return redirect(role_home_name(request.user, request=request))

    if request.method == "POST":
        form = VenueInviteAcceptForm(request.POST)
        if form.is_valid():
            user = form.save(invite=invite)
            login(request, user)
            set_active_venue(request, invite.venue)
            messages.success(request, f"Welcome to {invite.venue.name}.")
            return redirect(role_home_name(user, request=request))
    else:
        form = VenueInviteAcceptForm()

    return render(
        request,
        "accounts/invite_accept.html",
        {
            "form": form,
            "invite": invite,
        },
    )
