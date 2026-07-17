import json
from datetime import time
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.checks import run_checks
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .middleware import SESSION_ACTIVITY_KEY
from .models import PushSubscription, StaffProfile, Venue, VenueMembership
from .tenancy import ACTIVE_VENUE_SESSION_KEY
from .testing import VenueScopedTestCase, attach_user_to_venue, create_test_venue
from apps.breakages.models import Breakage
from apps.checklists.models import Checklist, ChecklistTemplate
from apps.orders.models import Order, OrderItem
from apps.sales.models import PosIntegration, PosLocationMapping, SalesSnapshot
from apps.shifts.models import Shift
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


class DemoDataBootstrapCommandTests(TestCase):
    @override_settings(ALLOW_DEMO_ACCOUNT_BOOTSTRAP=False)
    def test_bootstrap_demo_data_disabled_in_hardened_env(self):
        with self.assertRaises(CommandError):
            call_command("bootstrap_demo_data")

    @override_settings(ALLOW_DEMO_ACCOUNT_BOOTSTRAP=True)
    def test_bootstrap_demo_data_creates_realistic_records(self):
        stdout = StringIO()
        call_command("bootstrap_demo_data", stdout=stdout)

        self.assertTrue(Supplier.objects.filter(notes__contains="[DEMO_PREVIEW]").exists())
        self.assertTrue(StockItem.objects.filter(notes__contains="[DEMO_PREVIEW]").exists())
        self.assertTrue(Order.objects.filter(notes__contains="[DEMO_PREVIEW]").exists())
        self.assertTrue(Checklist.objects.filter(notes__contains="[DEMO_PREVIEW]").exists())
        self.assertTrue(Shift.objects.filter(notes__contains="[DEMO_PREVIEW]").exists())
        self.assertTrue(Breakage.objects.filter(notes__contains="[DEMO_PREVIEW]").exists())
        self.assertTrue(SalesSnapshot.objects.filter(notes__contains="[DEMO_PREVIEW]").exists())
        self.assertTrue(PosIntegration.objects.filter(notes__contains="[DEMO_PREVIEW]").exists())
        self.assertTrue(PosLocationMapping.objects.filter(integration__notes__contains="[DEMO_PREVIEW]").exists())
        self.assertIn("Demo preview dataset ready", stdout.getvalue())

    @override_settings(ALLOW_DEMO_ACCOUNT_BOOTSTRAP=True)
    def test_bootstrap_demo_data_replaces_previous_preview_records(self):
        call_command("bootstrap_demo_data")
        supplier_count = Supplier.objects.filter(notes__contains="[DEMO_PREVIEW]").count()
        stock_count = StockItem.objects.filter(notes__contains="[DEMO_PREVIEW]").count()
        order_count = Order.objects.filter(notes__contains="[DEMO_PREVIEW]").count()
        sales_count = SalesSnapshot.objects.filter(notes__contains="[DEMO_PREVIEW]").count()
        connector_count = PosIntegration.objects.filter(notes__contains="[DEMO_PREVIEW]").count()

        call_command("bootstrap_demo_data")

        self.assertEqual(
            Supplier.objects.filter(notes__contains="[DEMO_PREVIEW]").count(),
            supplier_count,
        )
        self.assertEqual(
            StockItem.objects.filter(notes__contains="[DEMO_PREVIEW]").count(),
            stock_count,
        )
        self.assertEqual(
            Order.objects.filter(notes__contains="[DEMO_PREVIEW]").count(),
            order_count,
        )
        self.assertEqual(
            SalesSnapshot.objects.filter(notes__contains="[DEMO_PREVIEW]").count(),
            sales_count,
        )
        self.assertEqual(
            PosIntegration.objects.filter(notes__contains="[DEMO_PREVIEW]").count(),
            connector_count,
        )


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

    def test_new_user_is_not_auto_attached_to_existing_venue(self):
        create_test_venue()
        user = User.objects.create_user(username="staff_b", password="strong-pass-123")

        self.assertFalse(user.venue_memberships.exists())


class RoleRoutingTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        self.staff_user = self.create_user(
            username="staff_member",
            password="strong-pass-123",
        )

        self.manager_user = self.create_user(
            username="manager_member",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )

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

    def test_management_mobile_dock_uses_operational_deep_links(self):
        self.client.login(username="manager_member", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:management_portal"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [link["label"] for link in response.context["mobile_dock_links"]],
            ["Today", "Sign-off", "Cellar", "Deliveries"],
        )
        self.assertEqual(
            response.context["mobile_dock_links"][1]["url"],
            f"{reverse('checklists:list')}?preset=today&status=pending#checklists-section-board",
        )
        self.assertEqual(
            response.context["mobile_command_links"][0]["label"],
            "Rota",
        )

    def test_staff_mobile_dock_uses_shift_deep_links(self):
        self.client.login(username="staff_member", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:staff_portal"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [link["label"] for link in response.context["mobile_dock_links"]],
            ["Today", "Tasks", "Stock", "Rota"],
        )
        self.assertEqual(
            response.context["mobile_dock_links"][2]["url"],
            f"{reverse('stock:list')}#stock-section-board",
        )
        self.assertEqual(
            response.context["mobile_command_links"][0]["label"],
            "Requests",
        )


class LoginSecurityTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.staff_user = self.create_user(
            username="secure_staff",
            password="strong-pass-123",
        )
        self.manager_user = self.create_user(
            username="secure_manager",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )
        self.landlord_user = self.create_superuser_with_membership(
            username="secure_landlord",
            email="secure_landlord@example.com",
            password="strong-pass-123",
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    @override_settings(
        LOGIN_THROTTLE_FAILURE_LIMIT=3,
        LOGIN_THROTTLE_WINDOW_SECONDS=600,
        LOGIN_THROTTLE_LOCKOUT_SECONDS=600,
    )
    def test_login_throttle_locks_after_repeated_failures(self):
        for attempt in range(2):
            response = self.client.post(
                reverse("login"),
                {"username": "secure_staff", "password": "wrong-pass"},
            )
            self.assertEqual(response.status_code, 200, attempt)

        response = self.client.post(
            reverse("login"),
            {"username": "secure_staff", "password": "wrong-pass"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertContains(
            response,
            "Too many sign-in attempts",
            status_code=429,
        )
        self.assertIn("Retry-After", response.headers)
        self.assertGreater(int(response.headers["Retry-After"]), 0)

        locked_response = self.client.post(
            reverse("login"),
            {"username": "secure_staff", "password": "strong-pass-123"},
        )
        self.assertEqual(locked_response.status_code, 429)

    @override_settings(SESSION_IDLE_TIMEOUT_SECONDS=60)
    def test_idle_session_is_logged_out_and_redirected_to_login(self):
        self.client.login(username="secure_staff", password="strong-pass-123")
        session = self.client.session
        session[SESSION_ACTIVITY_KEY] = int(timezone.now().timestamp()) - 120
        session.save()

        response = self.client.get(reverse("dashboard:staff_portal"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('dashboard:staff_portal')}",
            fetch_redirect_response=False,
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_non_superusers_cannot_access_django_admin(self):
        self.client.login(username="secure_manager", password="strong-pass-123")
        response = self.client.get("/admin/", follow=False)
        self.assertIn(response.status_code, {302, 403})

    def test_superuser_can_access_django_admin(self):
        self.client.login(username="secure_landlord", password="strong-pass-123")
        response = self.client.get("/admin/", follow=False)
        self.assertEqual(response.status_code, 200)


class SettingsAndPushTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        self.staff_user = self.create_user(
            username="notify_staff",
            password="strong-pass-123",
        )
        self.manager_user = self.create_user(
            username="notify_manager",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )

    def test_staff_can_access_settings_page(self):
        self.client.login(username="notify_staff", password="strong-pass-123")
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Device Alerts")
        self.assertContains(response, 'name="csrf-token"')

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


class VenueOnboardingFlowTests(TestCase):
    def test_first_time_setup_creates_seeded_venue_configuration(self):
        founder = User.objects.create_user(
            username="founder",
            password="strong-pass-123",
            email="founder@barrelboss.test",
        )
        self.client.login(username="founder", password="strong-pass-123")
        response = self.client.post(
            reverse("venue_setup"),
            {
                "organisation_name": "North Star Group",
                "venue_name": "River Bar",
                "venue_slug": "",
                "dashboard_focus": Venue.DashboardFocus.TRADE,
                "default_shift_start_time": "10:00",
                "default_shift_end_time": "23:00",
                "low_stock_buffer_percent": 35,
                "opening_handover_prompt": "Open, prep, and glassware checks completed.",
                "closing_handover_prompt": "Close, cash, and cellar notes handed over.",
                "supplier_names": "Brewline\nCellar Fresh",
                "manager_invite_emails": "manager.one@example.com",
                "staff_invite_emails": "staff.one@example.com\nstaff.two@example.com",
                "opening_checklist_items": "Unlock cellar",
                "closing_checklist_items": "Lock spirit cage",
                "delivery_checklist_items": "Receive keg delivery",
                "stock_seed_items": (
                    "Guinness 50L | Beer Barrels | Barrels | 4\n"
                    "House Gin | Spirits | Bottles | 3"
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard:management_portal"),
            fetch_redirect_response=False,
        )
        venue = Venue.objects.get(name="River Bar")
        self.assertEqual(self.client.session[ACTIVE_VENUE_SESSION_KEY], venue.id)
        self.assertEqual(venue.dashboard_focus, Venue.DashboardFocus.TRADE)
        self.assertEqual(venue.low_stock_buffer_percent, 35)
        self.assertEqual(venue.default_shift_start_time.strftime("%H:%M"), "10:00")
        self.assertEqual(venue.default_shift_end_time.strftime("%H:%M"), "23:00")
        self.assertEqual(
            VenueMembership.objects.get(user=founder, venue=venue).role,
            StaffProfile.Role.MANAGER,
        )
        self.assertEqual(venue.suppliers.count(), 2)
        self.assertEqual(
            set(
                venue.checklist_templates.values_list("checklist_type", flat=True)
            ),
            {
                Checklist.ChecklistType.OPENING,
                Checklist.ChecklistType.CLOSING,
                Checklist.ChecklistType.DELIVERY,
            },
        )
        self.assertEqual(
            venue.invites.filter(role=StaffProfile.Role.MANAGER).count(),
            1,
        )
        self.assertEqual(
            venue.invites.filter(role=StaffProfile.Role.STAFF).count(),
            2,
        )
        self.assertTrue(
            venue.stock_items.filter(
                name="Guinness 50L",
                category=StockItem.Category.BEER_BARRELS,
                minimum_level=4,
            ).exists()
        )
        self.assertTrue(
            ChecklistTemplate.objects.filter(
                venue=venue,
                title="Receive keg delivery",
                checklist_type=Checklist.ChecklistType.DELIVERY,
            ).exists()
        )


class VenueSwitchingAndIsolationTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        self.manager_user = self.create_user(
            username="multi_manager",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )
        self.staff_user = self.create_user(
            username="multi_staff",
            password="strong-pass-123",
        )
        self.second_venue = Venue.objects.create(
            organisation=self.venue.organisation,
            name="Garden Bar",
            slug="garden-bar",
            low_stock_buffer_percent=30,
            dashboard_focus=Venue.DashboardFocus.OPERATIONS,
            opening_handover_prompt="Garden bar opening checks complete.",
            closing_handover_prompt="Garden bar closing notes recorded.",
        )
        attach_user_to_venue(
            self.manager_user,
            self.second_venue,
            role=StaffProfile.Role.MANAGER,
            is_default=False,
        )
        attach_user_to_venue(
            self.staff_user,
            self.second_venue,
            role=StaffProfile.Role.STAFF,
            is_default=False,
        )

        self.main_supplier = Supplier.objects.create(name="Main Supplier", venue=self.venue)
        self.garden_supplier = Supplier.objects.create(name="Garden Supplier", venue=self.second_venue)
        self.main_stock = StockItem.objects.create(
            venue=self.venue,
            name="Main Lager",
            category=StockItem.Category.BEER_BARRELS,
            quantity=2,
            minimum_level=4,
            unit=StockItem.Unit.BARRELS,
            cost="99.00",
            supplier=self.main_supplier,
        )
        self.garden_stock = StockItem.objects.create(
            venue=self.second_venue,
            name="Garden Gin",
            category=StockItem.Category.SPIRITS,
            quantity=5,
            minimum_level=2,
            unit=StockItem.Unit.BOTTLES,
            cost="24.00",
            supplier=self.garden_supplier,
        )
        self.main_task = Checklist.objects.create(
            venue=self.venue,
            title="Main opening checks",
            checklist_type=Checklist.ChecklistType.OPENING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=timezone.localdate(),
        )
        self.garden_task = Checklist.objects.create(
            venue=self.second_venue,
            title="Garden close checks",
            checklist_type=Checklist.ChecklistType.CLOSING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=timezone.localdate(),
        )
        self.main_shift = Shift.objects.create(
            venue=self.venue,
            staff=self.staff_user,
            shift_date=timezone.localdate(),
            start_time=time(16, 0),
            end_time=time(22, 0),
            break_minutes=30,
            notes="Main floor",
            created_by=self.manager_user,
        )
        self.garden_shift = Shift.objects.create(
            venue=self.second_venue,
            staff=self.staff_user,
            shift_date=timezone.localdate(),
            start_time=time(12, 0),
            end_time=time(18, 0),
            break_minutes=30,
            notes="Garden terrace",
            created_by=self.manager_user,
        )
        self.main_order = Order.objects.create(
            venue=self.venue,
            supplier=self.main_supplier,
            created_by=self.manager_user,
            status=Order.Status.DRAFT,
        )
        OrderItem.objects.create(order=self.main_order, stock_item=self.main_stock, quantity=2)
        self.garden_order = Order.objects.create(
            venue=self.second_venue,
            supplier=self.garden_supplier,
            created_by=self.manager_user,
            status=Order.Status.DRAFT,
        )
        OrderItem.objects.create(order=self.garden_order, stock_item=self.garden_stock, quantity=1)

    def test_switch_venue_changes_visible_operational_scope(self):
        self.client.login(username="multi_manager", password="strong-pass-123")

        stock_response = self.client.get(reverse("stock:list"))
        order_response = self.client.get(reverse("orders:list"))
        checklist_response = self.client.get(reverse("checklists:list"))
        shift_response = self.client.get(reverse("shifts:list"))

        self.assertContains(stock_response, "Main Lager")
        self.assertNotContains(stock_response, "Garden Gin")
        self.assertContains(order_response, self.main_order.reference)
        self.assertNotContains(order_response, self.garden_order.reference)
        self.assertContains(checklist_response, "Main opening checks")
        self.assertNotContains(checklist_response, "Garden close checks")
        self.assertContains(shift_response, "Main floor")
        self.assertNotContains(shift_response, "Garden terrace")

        switch_response = self.client.get(reverse("switch_venue", args=[self.second_venue.id]))
        self.assertRedirects(
            switch_response,
            reverse("dashboard:management_portal"),
            fetch_redirect_response=False,
        )

        stock_response = self.client.get(reverse("stock:list"))
        order_response = self.client.get(reverse("orders:list"))
        checklist_response = self.client.get(reverse("checklists:list"))
        shift_response = self.client.get(reverse("shifts:list"))

        self.assertContains(stock_response, "Garden Gin")
        self.assertNotContains(stock_response, "Main Lager")
        self.assertContains(order_response, self.garden_order.reference)
        self.assertNotContains(order_response, self.main_order.reference)
        self.assertContains(checklist_response, "Garden close checks")
        self.assertNotContains(checklist_response, "Main opening checks")
        self.assertContains(shift_response, "Garden terrace")
        self.assertNotContains(shift_response, "Main floor")

    def test_active_venue_blocks_cross_venue_primary_key_access(self):
        self.client.login(username="multi_manager", password="strong-pass-123")
        self.client.get(reverse("switch_venue", args=[self.second_venue.id]))

        self.assertEqual(
            self.client.get(reverse("stock:edit", args=[self.main_stock.id])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("checklists:edit", args=[self.main_task.id])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("orders:edit", args=[self.main_order.id])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("shifts:edit", args=[self.main_shift.id])).status_code,
            404,
        )


class StaffManagementTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        self.manager_user = self.create_user(
            username="team_manager",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )

        self.staff_user = self.create_user(
            username="team_staff",
            password="strong-pass-123",
            first_name="Taylor",
            last_name="Mills",
            email="team_staff@example.com",
            job_title="Bartender",
        )
        self.staff_user.staff_profile.phone = "07123456789"
        self.staff_user.staff_profile.save(update_fields=["phone"])

    def test_manager_can_view_staff_list(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(reverse("staff"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "team_staff")
        self.assertContains(response, "Bartender")
        self.assertEqual(response.context["team_active_rate"], 100)
        self.assertFalse(response.context["filters_active"])

    def test_staff_list_context_exposes_active_filter_summary(self):
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(
            reverse("staff"),
            {"q": "team_staff", "status": "active", "alerts": "enabled"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["filters_active"])
        self.assertEqual(response.context["active_filter_count"], 3)
        self.assertEqual(response.context["selected_status_label"], "Active")
        self.assertEqual(response.context["selected_alerts_label"], "Alerts Enabled")
        self.assertIn("label", response.context["join_trend"])
        self.assertTrue(response.context["attention_items"])
        self.assertEqual(len(response.context["joined_chart"]), 7)

    def test_staff_preset_filters_inactive_profiles(self):
        inactive_user = self.create_user(
            username="inactive_member",
            password="strong-pass-123",
            is_active=False,
            notify_on_shift_assignment=False,
        )

        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(reverse("staff"), {"preset": "inactive"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "inactive_member")
        self.assertNotContains(response, "team_staff")
        self.assertEqual(response.context["selected_preset_label"], "Inactive")
        self.assertTrue(response.context["filter_presets"][0]["active"])

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
            extra_user = self.create_user(
                username=f"team_member_{index}",
                password="strong-pass-123",
                job_title="Bar Staff",
            )

        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(reverse("staff"), {"page": 2, "status": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["pagination_query"], "status=all")

    def test_manager_cannot_edit_landlord_profile(self):
        landlord = self.create_superuser_with_membership(
            username="owner_account",
            email="owner@barrelboss.test",
            password="strong-pass-123",
        )
        self.client.login(username="team_manager", password="strong-pass-123")
        response = self.client.get(reverse("staff_edit", args=[landlord.id]))

        self.assertRedirects(response, reverse("staff"), fetch_redirect_response=False)


class ReportsPageTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        self.staff_user = self.create_user(
            username="reports_staff",
            password="strong-pass-123",
        )
        self.manager_user = self.create_user(
            username="reports_manager",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )

        supplier = Supplier.objects.create(name="Brewline", venue=self.venue)
        stock_item = StockItem.objects.create(
            name="Carling Keg",
            venue=self.venue,
            category=StockItem.Category.BEER_BARRELS,
            quantity=3,
            minimum_level=6,
            unit=StockItem.Unit.BARRELS,
            cost="110.00",
            supplier=supplier,
        )
        order = Order.objects.create(
            venue=self.venue,
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
        self.assertContains(response, "Reports")
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
