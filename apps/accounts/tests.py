import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import PushSubscription, StaffProfile


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

    def test_staff_login_redirects_to_staff_portal(self):
        response = self.client.post(
            reverse("login"),
            {"username": "staff_member", "password": "strong-pass-123"},
        )
        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )

    def test_manager_login_redirects_to_management_portal(self):
        response = self.client.post(
            reverse("login"),
            {"username": "manager_member", "password": "strong-pass-123"},
        )
        self.assertRedirects(
            response,
            reverse("dashboard:management_portal"),
            fetch_redirect_response=False,
        )

    def test_staff_cannot_access_management_page(self):
        self.client.login(username="staff_member", password="strong-pass-123")
        response = self.client.get(reverse("suppliers:list"))
        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )

    def test_manager_can_access_management_page(self):
        self.client.login(username="manager_member", password="strong-pass-123")
        response = self.client.get(reverse("suppliers:list"))
        self.assertEqual(response.status_code, 200)


class SettingsAndPushTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="notify_staff",
            password="strong-pass-123",
        )
        self.manager_user = User.objects.create_user(
            username="notify_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

    def test_staff_can_access_settings_page(self):
        self.client.login(username="notify_staff", password="strong-pass-123")
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Device Alerts")

    def test_manager_can_update_team_shift_alert_preferences(self):
        self.client.login(username="notify_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("settings"),
            {"action": "team_shift_alerts"},
        )
        self.assertRedirects(response, reverse("settings"), fetch_redirect_response=False)
        self.staff_user.staff_profile.refresh_from_db()
        self.assertFalse(self.staff_user.staff_profile.notify_on_shift_assignment)

    @patch("taptrack.views.push_notifications_configured", return_value=True)
    def test_push_subscribe_creates_subscription(self, _mock_config):
        self.client.login(username="notify_staff", password="strong-pass-123")
        response = self.client.post(
            reverse("push_subscribe"),
            data=json.dumps(
                {
                    "subscription": {
                        "endpoint": "https://example.com/push/abc123",
                        "keys": {
                            "p256dh": "p256dh-key",
                            "auth": "auth-key",
                        },
                    }
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            PushSubscription.objects.filter(
                user=self.staff_user,
                endpoint="https://example.com/push/abc123",
            ).exists()
        )

    def test_push_subscribe_returns_503_if_server_not_configured(self):
        self.client.login(username="notify_staff", password="strong-pass-123")
        response = self.client.post(
            reverse("push_subscribe"),
            data=json.dumps({"subscription": {}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)

    def test_push_unsubscribe_removes_current_user_subscription(self):
        PushSubscription.objects.create(
            user=self.staff_user,
            endpoint="https://example.com/push/remove-me",
            p256dh="p256dh-key",
            auth="auth-key",
        )
        self.client.login(username="notify_staff", password="strong-pass-123")
        response = self.client.post(
            reverse("push_unsubscribe"),
            data=json.dumps({"endpoint": "https://example.com/push/remove-me"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            PushSubscription.objects.filter(
                endpoint="https://example.com/push/remove-me",
                user=self.staff_user,
            ).exists()
        )
