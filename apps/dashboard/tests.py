from datetime import time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffProfile
from apps.breakages.models import Breakage
from apps.checklists.models import Checklist
from apps.orders.models import Order, OrderItem
from apps.shifts.models import Shift
from apps.stock.models import StockItem
from apps.suppliers.models import Supplier


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
        self.assertEqual(len(response.context["metrics"]), 4)
        self.assertContains(response, "Management Overview")

    def test_staff_portal_context(self):
        self.client.login(username="dash_staff", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:staff_portal"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["management_view"])
        self.assertEqual(response.context["portal_title"], "Staff Portal")
        self.assertEqual(len(response.context["quick_actions"]), 3)
        self.assertContains(response, "Staff Shift Overview")

    def test_staff_cannot_access_management_portal(self):
        self.client.login(username="dash_staff", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:management_portal"))
        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )


class DashboardDataDrivenMetricsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="metric_staff",
            password="strong-pass-123",
        )
        self.manager_user = User.objects.create_user(
            username="metric_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        supplier = Supplier.objects.create(name="Metric Brewline")
        stock_item = StockItem.objects.create(
            name="Metric Lager Barrel",
            category=StockItem.Category.BEER_BARRELS,
            quantity=1,
            minimum_level=4,
            unit=StockItem.Unit.BARRELS,
            cost="120.00",
            supplier=supplier,
        )
        order = Order.objects.create(
            supplier=supplier,
            created_by=self.staff_user,
            status=Order.Status.DRAFT,
            order_date=timezone.localdate(),
            delivery_date=timezone.localdate(),
        )
        OrderItem.objects.create(order=order, stock_item=stock_item, quantity=2)

        Shift.objects.create(
            staff=self.staff_user,
            shift_date=timezone.localdate(),
            start_time=time(12, 0),
            end_time=time(20, 0),
            break_minutes=30,
            created_by=self.manager_user,
        )

        Checklist.objects.create(
            title="Close till review",
            checklist_type=Checklist.ChecklistType.CLOSING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=timezone.localdate(),
            completed=False,
        )

        Breakage.objects.create(
            item_name="Pint glass",
            quantity=1,
            issue_type=Breakage.IssueType.BROKEN,
            reported_by=self.staff_user,
        )

    def test_management_portal_uses_live_operational_counts(self):
        self.client.login(username="metric_manager", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:management_portal"))

        self.assertEqual(response.status_code, 200)
        metrics_by_label = {
            metric["label"]: metric["value"] for metric in response.context["metrics"]
        }
        self.assertEqual(metrics_by_label["Low Stock Items"], 1)
        self.assertEqual(metrics_by_label["Order Requests Awaiting Approval"], 1)
        self.assertEqual(metrics_by_label["Breakages This Week"], 1)
        self.assertEqual(len(response.context["throughput"]), 7)

    def test_staff_portal_uses_live_personal_counts(self):
        self.client.login(username="metric_staff", password="strong-pass-123")
        response = self.client.get(reverse("dashboard:staff_portal"))

        self.assertEqual(response.status_code, 200)
        metrics_by_label = {
            metric["label"]: metric["value"] for metric in response.context["metrics"]
        }
        self.assertEqual(metrics_by_label["My Open Order Requests"], 1)
        self.assertEqual(metrics_by_label["My Tasks Due Today"], 1)
        self.assertEqual(metrics_by_label["My Breakages This Week"], 1)
        self.assertEqual(metrics_by_label["Hours This Week"], "7.5")
