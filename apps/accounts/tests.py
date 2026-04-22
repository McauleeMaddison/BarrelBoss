from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import StaffProfile


class StaffProfileSignalTests(TestCase):
    def test_profile_created_for_standard_user(self):
        user = User.objects.create_user(username="staff_a", password="strong-pass-123")
        self.assertTrue(hasattr(user, "staff_profile"))
        self.assertEqual(user.staff_profile.role, StaffProfile.Role.STAFF)

    def test_profile_created_for_superuser_as_landlord(self):
        user = User.objects.create_superuser(
            username="owner_a",
            email="owner@example.com",
            password="strong-pass-123",
        )
        self.assertEqual(user.staff_profile.role, StaffProfile.Role.LANDLORD)


class RoleRoutingTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff_member",
            password="strong-pass-123",
        )

        self.manager_user = User.objects.create_user(
            username="manager_member",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

    def test_staff_login_redirects_to_checklists(self):
        response = self.client.post(
            reverse("login"),
            {"username": "staff_member", "password": "strong-pass-123"},
        )
        self.assertRedirects(
            response,
            reverse("checklists:list"),
            fetch_redirect_response=False,
        )

    def test_manager_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "manager_member", "password": "strong-pass-123"},
        )
        self.assertRedirects(
            response,
            reverse("dashboard:home"),
            fetch_redirect_response=False,
        )

    def test_staff_cannot_access_management_page(self):
        self.client.login(username="staff_member", password="strong-pass-123")
        response = self.client.get(reverse("orders:list"))
        self.assertRedirects(
            response,
            reverse("checklists:list"),
            fetch_redirect_response=False,
        )

    def test_manager_can_access_management_page(self):
        self.client.login(username="manager_member", password="strong-pass-123")
        response = self.client.get(reverse("orders:list"))
        self.assertEqual(response.status_code, 200)
