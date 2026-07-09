from .tenancy import resolve_active_membership


class ActiveVenueMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_membership = None
        request.active_venue = None
        request.active_organisation = None

        if getattr(request, "user", None) and request.user.is_authenticated:
            membership = resolve_active_membership(request)
            if membership:
                request.active_membership = membership
                request.active_venue = membership.venue
                request.active_organisation = membership.venue.organisation

        return self.get_response(request)
