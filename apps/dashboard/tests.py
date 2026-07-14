from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffProfile
from apps.accounts.testing import VenueScopedTestCase
from apps.breakages.models import Breakage
from apps.checklists.models import Checklist
from apps.orders.models import Order, OrderItem
from apps.sales.models import PosIntegration, PosLocationMapping, SalesSnapshot
from apps.shifts.models import Shift
from apps.stock.models import StockItem
from apps.suppliers.models import Supplier


class DashboardAccessTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        self.staff_user = self.create_user(
            username="dash_staff",
            password="strong-pass-123",
        )
        self.manager_user = self.create_user(
            username="dash_manager",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_home_redirects_manager_to_management_portal(self):
        self.client.login(username="dash_manager", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(
            response,
            reverse("dashboard:management_portal"),
            fetch_redirect_response=False,
        )

    def test_home_redirects_staff_to_staff_portal(self):
        self.client.login(username="dash_staff", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )

    def test_manager_portal_context(self):
        self.client.login(username="dash_manager", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:management_portal"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["management_view"])
        self.assertEqual(response.context["portal_title"], "Management Portal")
        self.assertEqual(len(response.context["portal_sections"]), 4)
        self.assertEqual(len(response.context["metrics"]), 4)
        self.assertIn("state", response.context["metrics"][0])
        self.assertIn("trend", response.context["metrics"][0])
        self.assertIn("chart_points", response.context["metrics"][0])
        self.assertIn("actions", response.context["metrics"][0])
        self.assertTrue(response.context["attention_items"])
        self.assertContains(response, "Management Overview")
        self.assertContains(response, "Operational Control Board")
        self.assertContains(response, "Cellar watch")

    def test_staff_portal_context(self):
        self.client.login(username="dash_staff", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:staff_portal"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["management_view"])
        self.assertEqual(response.context["portal_title"], "Staff Portal")
        self.assertEqual(len(response.context["portal_sections"]), 4)
        self.assertIn("state", response.context["metrics"][0])
        self.assertIn("trend", response.context["metrics"][0])
        self.assertIn("chart_points", response.context["metrics"][0])
        self.assertIn("actions", response.context["metrics"][0])
        self.assertTrue(response.context["attention_items"])
        self.assertContains(response, "Today")
        self.assertContains(response, "Workspace")
        self.assertContains(response, "View stock")

    def test_staff_cannot_access_management_portal(self):
        self.client.login(username="dash_staff", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:management_portal"))
        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )


class DashboardDataDrivenMetricsTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        self.staff_user = self.create_user(
            username="metric_staff",
            password="strong-pass-123",
        )
        self.manager_user = self.create_user(
            username="metric_manager",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )

        supplier = Supplier.objects.create(name="Metric Brewline", venue=self.venue)
        stock_item = StockItem.objects.create(
            venue=self.venue,
            name="Metric Lager Barrel",
            category=StockItem.Category.BEER_BARRELS,
            quantity=1,
            minimum_level=4,
            unit=StockItem.Unit.BARRELS,
            cost="120.00",
            supplier=supplier,
        )
        order = Order.objects.create(
            venue=self.venue,
            supplier=supplier,
            created_by=self.staff_user,
            status=Order.Status.DRAFT,
            order_date=timezone.localdate(),
            delivery_date=timezone.localdate(),
        )
        OrderItem.objects.create(order=order, stock_item=stock_item, quantity=2)

        Shift.objects.create(
            venue=self.venue,
            staff=self.staff_user,
            shift_date=timezone.localdate(),
            start_time=time(12, 0),
            end_time=time(20, 0),
            break_minutes=30,
            created_by=self.manager_user,
        )

        Checklist.objects.create(
            venue=self.venue,
            title="Close till review",
            checklist_type=Checklist.ChecklistType.CLOSING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=timezone.localdate(),
            completed=False,
        )

        Breakage.objects.create(
            venue=self.venue,
            item_name="Pint glass",
            quantity=1,
            issue_type=Breakage.IssueType.BROKEN,
            reported_by=self.staff_user,
        )
        SalesSnapshot.objects.create(
            venue=self.venue,
            business_date=timezone.localdate(),
            source=SalesSnapshot.Source.TOAST,
            sync_mode=SalesSnapshot.SyncMode.LIVE,
            net_sales="1680.00",
            gross_sales="1730.00",
            discounts="20.00",
            refunds="30.00",
            tips="180.00",
            transactions=126,
            covers=102,
            cash_sales="180.00",
            card_sales="1380.00",
            digital_sales="120.00",
            beer_sales="760.00",
            spirits_sales="340.00",
            wine_sales="180.00",
            soft_sales="170.00",
            food_sales="140.00",
            other_sales="90.00",
            uploaded_by=self.manager_user,
        )
        integration = PosIntegration.objects.create(
            venue=self.venue,
            label="Toast Control Feed",
            provider=PosIntegration.Provider.TOAST,
            account_identifier="toast-control",
            webhook_secret="control-secret",
            sync_interval_minutes=15,
            is_enabled=True,
            auto_sync_enabled=True,
            webhook_enabled=True,
            last_synced_at=timezone.now() - timedelta(minutes=5),
            last_success_at=timezone.now() - timedelta(minutes=5),
            created_by=self.manager_user,
        )
        PosLocationMapping.objects.create(
            integration=integration,
            external_location_id="toast-main",
            external_location_name="Toast Main",
            internal_location_name="Main Bar",
            is_primary=True,
            is_active=True,
            auto_import_enabled=True,
        )

    def test_management_portal_uses_live_operational_counts(self):
        self.client.login(username="metric_manager", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:management_portal"))

        self.assertEqual(response.status_code, 200)
        metrics_by_label = {
            metric["label"]: metric["value"] for metric in response.context["metrics"]
        }
        self.assertEqual(metrics_by_label["Net Sales Today"], "£1,680")
        self.assertEqual(metrics_by_label["Low Stock Items"], 1)
        self.assertEqual(metrics_by_label["Order Requests Awaiting Approval"], 1)
        self.assertEqual(metrics_by_label["Shifts Scheduled This Week"], 1)
        self.assertEqual(len(response.context["portal_sections"]), 4)
        self.assertContains(response, "Metric Lager Barrel")
        self.assertContains(response, "Toast Control Feed")

    def test_staff_portal_uses_live_personal_counts(self):
        self.client.login(username="metric_staff", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:staff_portal"))

        self.assertEqual(response.status_code, 200)
        metrics_by_label = {
            metric["label"]: metric["value"] for metric in response.context["metrics"]
        }
        self.assertEqual(metrics_by_label["My Tasks"], 1)
        self.assertEqual(metrics_by_label["Stock"], "View")
        self.assertEqual(metrics_by_label["Hours This Week"], "7.5")
        self.assertEqual(metrics_by_label["Next Shift"], "12:00")
        self.assertEqual(len(response.context["portal_sections"]), 4)
        self.assertContains(response, "Close till review")
        self.assertContains(response, "Request stock")
        self.assertContains(response, "View stock")
