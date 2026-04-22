from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StaffProfile


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="dash_staff",
            password="strong-pass-123",
        )
        self.manager_user = User.objects.create_user(
            username="dash_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_manager_dashboard_context(self):
        self.client.login(username="dash_manager", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["management_view"])
        self.assertEqual(len(response.context["metrics"]), 4)
        self.assertContains(response, "Management Overview")

    def test_staff_dashboard_context(self):
        self.client.login(username="dash_staff", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["management_view"])
        self.assertEqual(len(response.context["quick_actions"]), 3)
        self.assertContains(response, "Staff Shift Overview")
