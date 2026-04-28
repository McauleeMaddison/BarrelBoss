import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.checks import run_checks
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import PushSubscription, StaffProfile
from apps.orders.models import Order, OrderItem
from apps.stock.models import StockItem
from apps.suppliers.models import Supplier


class DemoAccountBootstrapCommandTests(TestCase):
    @override_settings(ALLOW_DEMO_ACCOUNT_BOOTSTRAP=False)
    def test_bootstrap_demo_accounts_disabled_by_default_in_hardened_env(self):
        with self.assertRaises(CommandError):
            call_command("bootstrap_demo_accounts")

        self.assertFalse(User.objects.filter(username="landlord").exists())
        self.assertFalse(User.objects.filter(username="manager").exists())
        self.assertFalse(User.objects.filter(username="staff").exists())

    @override_settings(ALLOW_DEMO_ACCOUNT_BOOTSTRAP=True)
    def test_bootstrap_demo_accounts_creates_expected_users(self):
        stdout = StringIO()
        call_command("bootstrap_demo_accounts", password="DemoStrongPass-123!", stdout=stdout)

        landlord = User.objects.get(username="landlord")
        manager = User.objects.get(username="manager")
        staff = User.objects.get(username="staff")

        self.assertTrue(landlord.is_superuser)
        self.assertEqual(landlord.staff_profile.role, StaffProfile.Role.LANDLORD)
        self.assertEqual(manager.staff_profile.role, StaffProfile.Role.MANAGER)
        self.assertEqual(staff.staff_profile.role, StaffProfile.Role.STAFF)
        self.assertTrue(landlord.check_password("DemoStrongPass-123!"))
        self.assertTrue(manager.check_password("DemoStrongPass-123!"))
        self.assertTrue(staff.check_password("DemoStrongPass-123!"))
        self.assertIn("Demo accounts ready", stdout.getvalue())


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


class StaffManagementTests(TestCase):
    def setUp(self):
        self.manager_user = User.objects.create_user(
            username="team_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        self.staff_user = User.objects.create_user(
            username="team_staff",
            password="strong-pass-123",
            first_name="Taylor",
            last_name="Mills",
            email="team_staff@example.com",
        )
        self.staff_user.staff_profile.job_title = "Bartender"
        self.staff_user.staff_profile.phone = "07123456789"
        self.staff_user.staff_profile.save(update_fields=["job_title", "phone"])

    def test_manager_can_view_staff_list(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(reverse("staff"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "team_staff")
        self.assertContains(response, "Bartender")

    def test_staff_cannot_access_staff_management(self):
        self.client.login(username="team_staff", password="strong-pass-123")
        response = self.client.get(reverse("staff"))
        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )

    def test_manager_can_create_staff_account(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("staff_add"),
            {
                "username": "new_team_member",
                "first_name": "Casey",
                "last_name": "Reid",
                "email": "casey@example.com",
                "password1": "NewStrongPass-123!",
                "password2": "NewStrongPass-123!",
                "role": StaffProfile.Role.STAFF,
                "job_title": "Barback",
                "phone": "07000000000",
                "is_active": "on",
                "notify_on_shift_assignment": "on",
                "notes": "Weekend support",
            },
        )

        self.assertRedirects(response, reverse("staff"), fetch_redirect_response=False)
        created_user = User.objects.get(username="new_team_member")
        self.assertEqual(created_user.staff_profile.job_title, "Barback")
        self.assertTrue(created_user.staff_profile.is_active)

    def test_manager_cannot_create_landlord_role(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("staff_add"),
            {
                "username": "bad_landlord_attempt",
                "first_name": "No",
                "last_name": "Access",
                "email": "denied@example.com",
                "password1": "AnotherStrongPass-123!",
                "password2": "AnotherStrongPass-123!",
                "role": StaffProfile.Role.LANDLORD,
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="bad_landlord_attempt").exists())
        self.assertContains(response, "Select a valid choice")

    def test_manager_can_edit_staff_account(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("staff_edit", args=[self.staff_user.id]),
            {
                "first_name": "Taylor",
                "last_name": "Mills",
                "email": "updated_staff@example.com",
                "role": StaffProfile.Role.STAFF,
                "job_title": "Senior Bartender",
                "phone": "07999999999",
                "is_active": "on",
                "notify_on_shift_assignment": "on",
                "notes": "Promoted this month",
            },
        )

        self.assertRedirects(response, reverse("staff"), fetch_redirect_response=False)
        self.staff_user.refresh_from_db()
        self.assertEqual(self.staff_user.email, "updated_staff@example.com")
        self.assertEqual(self.staff_user.staff_profile.job_title, "Senior Bartender")

    def test_manager_can_toggle_staff_active_status(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.post(reverse("staff_toggle_active", args=[self.staff_user.id]))

        self.assertRedirects(response, reverse("staff"), fetch_redirect_response=False)
        self.staff_user.staff_profile.refresh_from_db()
        self.assertFalse(self.staff_user.staff_profile.is_active)

    def test_manager_cannot_deactivate_own_profile(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.post(reverse("staff_toggle_active", args=[self.manager_user.id]))

        self.assertRedirects(response, reverse("staff"), fetch_redirect_response=False)
        self.manager_user.staff_profile.refresh_from_db()
        self.assertTrue(self.manager_user.staff_profile.is_active)

    def test_manager_can_export_staff_csv(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(reverse("staff"), {"export": "csv"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("BarrelBoss Staff Export", response.content.decode("utf-8"))

    def test_staff_management_list_is_paginated(self):
        for index in range(20):
            extra_user = User.objects.create_user(
                username=f"team_member_{index}",
                password="strong-pass-123",
            )
            extra_user.staff_profile.job_title = "Bar Staff"
            extra_user.staff_profile.save(update_fields=["job_title"])

        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(reverse("staff"), {"page": 2, "status": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["pagination_query"], "status=all")

    def test_manager_cannot_edit_landlord_profile(self):
        landlord = User.objects.create_superuser(
            username="owner_account",
            email="owner@barrelboss.test",
            password="strong-pass-123",
        )
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(reverse("staff_edit", args=[landlord.id]))

        self.assertRedirects(response, reverse("staff"), fetch_redirect_response=False)


class ReportsPageTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="reports_staff",
            password="strong-pass-123",
        )
        self.manager_user = User.objects.create_user(
            username="reports_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        supplier = Supplier.objects.create(name="Brewline")
        stock_item = StockItem.objects.create(
            name="Carling Keg",
            category=StockItem.Category.BEER_BARRELS,
            quantity=3,
            minimum_level=6,
            unit=StockItem.Unit.BARRELS,
            cost="110.00",
            supplier=supplier,
        )
        order = Order.objects.create(
            supplier=supplier,
            created_by=self.manager_user,
            order_date=timezone.localdate(),
            status=Order.Status.DELIVERED,
        )
        OrderItem.objects.create(order=order, stock_item=stock_item, quantity=2)

    def test_manager_can_view_reports_page_with_enhanced_context(self):
        self.client.login(username="reports_manager", password="strong-pass-123")
        response = self.client.get(reverse("reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operational Performance Cockpit")
        self.assertEqual(len(response.context["report_kpi_cards"]), 5)
        self.assertGreaterEqual(len(response.context["executive_highlights"]), 4)

    def test_manager_can_export_reports_csv(self):
        self.client.login(username="reports_manager", password="strong-pass-123")
        response = self.client.get(reverse("reports"), {"range": "7", "export": "csv"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        self.assertIn("BarrelBoss Operational Report", response.content.decode("utf-8"))

    def test_staff_is_redirected_from_reports_page(self):
        self.client.login(username="reports_staff", password="strong-pass-123")
        response = self.client.get(reverse("reports"))

        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )


class DeploymentHardeningChecksTests(TestCase):
    def _deployment_check_ids(self):
        return {
            issue.id
            for issue in run_checks(include_deployment_checks=True)
            if issue.id and issue.id.startswith("accounts.E2")
        }

    @override_settings(
        DEBUG=False,
        ALLOW_DEMO_ACCOUNT_BOOTSTRAP=False,
        SECRET_KEY="Strong-Unique-Prod-Secret-1234567890",
        ALLOWED_HOSTS=["barrelboss.example.com"],
        CSRF_TRUSTED_ORIGINS=["https://barrelboss.example.com"],
    )
    def test_hardened_settings_pass_custom_deploy_checks(self):
        self.assertEqual(self._deployment_check_ids(), set())

    @override_settings(
        DEBUG=False,
        ALLOW_DEMO_ACCOUNT_BOOTSTRAP=True,
        SECRET_KEY="Strong-Unique-Prod-Secret-1234567890",
        ALLOWED_HOSTS=["barrelboss.example.com"],
        CSRF_TRUSTED_ORIGINS=["https://barrelboss.example.com"],
    )
    def test_demo_bootstrap_enabled_fails_deploy_check(self):
        self.assertIn("accounts.E201", self._deployment_check_ids())

    @override_settings(
        DEBUG=False,
        ALLOW_DEMO_ACCOUNT_BOOTSTRAP=False,
        SECRET_KEY="django-insecure-unsafe-default",
        ALLOWED_HOSTS=["barrelboss.example.com"],
        CSRF_TRUSTED_ORIGINS=["https://barrelboss.example.com"],
    )
    def test_insecure_secret_key_fails_deploy_check(self):
        self.assertIn("accounts.E202", self._deployment_check_ids())

    @override_settings(
        DEBUG=False,
        ALLOW_DEMO_ACCOUNT_BOOTSTRAP=False,
        SECRET_KEY="Strong-Unique-Prod-Secret-1234567890",
        ALLOWED_HOSTS=["localhost", "127.0.0.1"],
        CSRF_TRUSTED_ORIGINS=["https://barrelboss.example.com"],
    )
    def test_local_only_allowed_hosts_fail_deploy_check(self):
        self.assertIn("accounts.E203", self._deployment_check_ids())

    @override_settings(
        DEBUG=False,
        ALLOW_DEMO_ACCOUNT_BOOTSTRAP=False,
        SECRET_KEY="Strong-Unique-Prod-Secret-1234567890",
        ALLOWED_HOSTS=["barrelboss.example.com"],
        CSRF_TRUSTED_ORIGINS=["http://barrelboss.example.com"],
    )
    def test_non_https_csrf_origins_fail_deploy_check(self):
        self.assertIn("accounts.E204", self._deployment_check_ids())
