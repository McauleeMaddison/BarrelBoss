from django.contrib.auth.views import LoginView
from django.urls import reverse

from .permissions import role_home_name


class RoleLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse(role_home_name(self.request.user))
