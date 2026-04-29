import os
import re
import unittest
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone

from apps.accounts.models import StaffProfile
from apps.checklists.models import Checklist
from apps.orders.models import Order, OrderItem
from apps.shifts.models import Shift
from apps.stock.models import StockItem
from apps.suppliers.models import Supplier

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import expect, sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PlaywrightError = Exception
    expect = None
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


User = get_user_model()


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BrowserSmokeTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        cls._playwright = None
        cls._browser = None
        cls._require_browser = _env_flag("E2E_REQUIRE_BROWSER", False)

        try:
            super().setUpClass()
        except OSError as exc:
            if cls._require_browser:
                raise RuntimeError(
                    f"Unable to start Django live server for E2E tests: {exc}"
                ) from exc
            raise unittest.SkipTest(f"Live server unavailable for E2E tests: {exc}") from exc

        if not PLAYWRIGHT_AVAILABLE:
            if cls._require_browser:
                raise RuntimeError("Playwright package is not installed.")
            raise unittest.SkipTest("Playwright is not installed")

        try:
            cls._playwright = sync_playwright().start()
            cls._browser = cls._playwright.chromium.launch(
                headless=_env_flag("E2E_HEADLESS", True)
            )
        except PlaywrightError as exc:
            if cls._playwright is not None:
                cls._playwright.stop()
            if cls._require_browser:
                raise RuntimeError(f"Playwright browser launch failed: {exc}") from exc
            raise unittest.SkipTest(f"Playwright browser not available: {exc}") from exc

    @classmethod
    def tearDownClass(cls):
        try:
            if getattr(cls, "_browser", None) is not None:
                cls._browser.close()
            if getattr(cls, "_playwright", None) is not None:
                cls._playwright.stop()
        finally:
            super().tearDownClass()

    def setUp(self):
        self._seed_data()
        self.context = self._browser.new_context(viewport={"width": 1440, "height": 960})
        self.page = self.context.new_page()
        self.page.set_default_timeout(12000)

    def tearDown(self):
        self.context.close()

    def _seed_data(self):
        self.manager_user, _ = User.objects.get_or_create(username="e2e_manager")
        self.manager_user.set_password("strong-pass-123")
        self.manager_user.is_active = True
        self.manager_user.save(update_fields=["password", "is_active"])
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        self.staff_user, _ = User.objects.get_or_create(username="e2e_staff")
        self.staff_user.set_password("strong-pass-123")
        self.staff_user.is_active = True
        self.staff_user.save(update_fields=["password", "is_active"])
        self.staff_user.staff_profile.role = StaffProfile.Role.STAFF
        self.staff_user.staff_profile.save(update_fields=["role"])

        self.supplier, _ = Supplier.objects.get_or_create(
            name="E2E Supplier",
            defaults={"category_supplied": Supplier.CategorySupplied.BEER_BARRELS},
        )

    def _stock_defaults(self):
        return {
            "quantity": 10,
            "unit": StockItem.Unit.BOTTLES,
            "minimum_level": 3,
            "cost": "12.50",
            "supplier": self.supplier,
            "is_active": True,
        }

    def _login(self, username, password):
        self.page.goto(f"{self.live_server_url}/accounts/login/")
        self.page.get_by_label("Username").fill(username)
        self.page.get_by_label("Password").fill(password)
        self.page.get_by_role("button", name="Sign In").click()

    def test_manager_can_complete_core_crud_flows(self):
        self._login("e2e_manager", "strong-pass-123")
        expect(self.page).to_have_url(re.compile(r".*/dashboard/management/$"))

        stock_name = "E2E Lager Keg"
        order_note = "E2E Smoke Order"
        checklist_title = "E2E Opening Cellar Check"
        shift_note = "E2E Shift Coverage"
        today = timezone.localdate()

        self.page.get_by_role("link", name="Stock").click()
        self.page.get_by_role("link", name="Add Item").click()
        self.page.locator("#id_name").fill(stock_name)
        self.page.locator("#id_category").select_option(label="Beer Barrels")
        self.page.locator("#id_quantity").fill("12")
        self.page.locator("#id_unit").select_option(label="Barrels")
        self.page.locator("#id_minimum_level").fill("6")
        self.page.locator("#id_cost").fill("129.50")
        self.page.locator("#id_supplier").select_option(label=self.supplier.name)
        self.page.locator("#id_last_restocked").fill(today.isoformat())
        self.page.locator("#id_notes").fill("Created via browser smoke test")
        self.page.get_by_role("button", name="Create Item").click()
        expect(self.page).to_have_url(re.compile(r".*/stock/$"))
        self.assertTrue(StockItem.objects.filter(name=stock_name, is_active=True).exists())

        self.page.get_by_role("link", name="Orders").click()
        self.page.get_by_role("link", name="Create Order").click()
        self.page.locator("#id_supplier").select_option(label=self.supplier.name)
        self.page.locator("#id_order_date").fill(today.isoformat())
        self.page.locator("#id_delivery_date").fill((today + timedelta(days=1)).isoformat())
        self.page.locator("#id_status").select_option(label="Ordered")
        self.page.locator("#id_notes").fill(order_note)
        self.page.locator("#id_items-0-stock_item").select_option(label=stock_name)
        self.page.locator("#id_items-0-quantity").fill("2")
        self.page.get_by_role("button", name="Create Order").click()
        expect(self.page).to_have_url(re.compile(r".*/orders/$"))
        created_order = Order.objects.filter(notes=order_note).first()
        self.assertIsNotNone(created_order)
        self.assertEqual(created_order.items.count(), 1)

        self.page.get_by_role("link", name="Checklists").click()
        self.page.get_by_role("link", name="Assign Task").click()
        self.page.locator("#id_title").fill(checklist_title)
        self.page.locator("#id_checklist_type").select_option(label="Opening")
        self.page.locator("#id_assigned_to").select_option(label=self.staff_user.username)
        self.page.locator("#id_due_date").fill(today.isoformat())
        self.page.locator("#id_notes").fill("Assigned from smoke flow")
        self.page.get_by_role("button", name="Assign Task").click()
        expect(self.page).to_have_url(re.compile(r".*/checklists/$"))
        self.assertTrue(Checklist.objects.filter(title=checklist_title).exists())

        self.page.get_by_role("link", name="Shifts").click()
        self.page.get_by_role("link", name="Schedule Shift").click()
        self.page.locator("#id_staff").select_option(label=self.staff_user.username)
        self.page.locator("#id_shift_date").fill(today.isoformat())
        self.page.locator("#id_start_time").fill("10:00")
        self.page.locator("#id_end_time").fill("18:00")
        self.page.locator("#id_break_minutes").fill("30")
        self.page.locator("#id_notes").fill(shift_note)
        self.page.get_by_role("button", name="Schedule Shift").click()
        expect(self.page).to_have_url(re.compile(r".*/shifts/$"))
        self.assertTrue(Shift.objects.filter(notes=shift_note, staff=self.staff_user).exists())

    def test_staff_redirects_to_staff_portal_and_cannot_open_management_pages(self):
        self._login("e2e_staff", "strong-pass-123")
        expect(self.page).to_have_url(re.compile(r".*/dashboard/staff/$"))

        self.page.goto(f"{self.live_server_url}/suppliers/")
        expect(self.page).to_have_url(re.compile(r".*/dashboard/staff/$"))
        expect(self.page.get_by_text("Access denied", exact=False)).to_be_visible()

    def test_manager_can_soft_delete_stock_item_from_ui(self):
        stock_item = StockItem.objects.create(
            name="E2E Delete Stock Item",
            category=StockItem.Category.SPIRITS,
            **self._stock_defaults(),
        )
        self._login("e2e_manager", "strong-pass-123")

        self.page.goto(f"{self.live_server_url}/stock/")
        row = self.page.locator("tr", has_text=stock_item.name).first
        row.get_by_role("link", name="Delete").click()
        expect(self.page).to_have_url(re.compile(r".*/stock/\d+/delete/$"))
        self.page.get_by_role("button", name="Confirm Remove").click()
        expect(self.page).to_have_url(re.compile(r".*/stock/$"))

        stock_item.refresh_from_db()
        self.assertFalse(stock_item.is_active)

    def test_stock_filter_pagination_keeps_query_parameters(self):
        for index in range(13):
            StockItem.objects.create(
                name=f"E2E Spirits {index:02d}",
                category=StockItem.Category.SPIRITS,
                **self._stock_defaults(),
            )
        StockItem.objects.create(
            name="E2E Beer Single",
            category=StockItem.Category.BEER_BARRELS,
            **self._stock_defaults(),
        )
        self._login("e2e_manager", "strong-pass-123")

        self.page.goto(f"{self.live_server_url}/stock/")
        self.page.locator("#q").fill("E2E Spirits")
        self.page.locator("#category").select_option(value=StockItem.Category.SPIRITS)
        self.page.get_by_role("button", name="Apply Filter").click()

        expect(self.page.get_by_text("Page 1 of 2")).to_be_visible()
        self.page.get_by_role("link", name="Next").click()
        expect(self.page.get_by_text("Page 2 of 2")).to_be_visible()

        parsed_url = urlparse(self.page.url)
        query_params = parse_qs(parsed_url.query)
        self.assertEqual(query_params.get("category"), [StockItem.Category.SPIRITS])
        self.assertEqual(query_params.get("q"), ["E2E Spirits"])
        self.assertEqual(query_params.get("page"), ["2"])

    def test_manager_can_delete_checklist_and_shift_records(self):
        today = timezone.localdate()
        checklist = Checklist.objects.create(
            title="E2E Checklist Delete",
            checklist_type=Checklist.ChecklistType.OPENING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=today,
            completed=False,
        )
        shift = Shift.objects.create(
            staff=self.staff_user,
            created_by=self.manager_user,
            shift_date=today,
            start_time=datetime.strptime("10:00", "%H:%M").time(),
            end_time=datetime.strptime("18:00", "%H:%M").time(),
            break_minutes=30,
            notes="E2E Shift Delete",
        )
        self._login("e2e_manager", "strong-pass-123")

        self.page.goto(f"{self.live_server_url}/checklists/")
        checklist_row = self.page.locator("tr", has_text=checklist.title).first
        checklist_row.get_by_role("link", name="Delete").click()
        expect(self.page).to_have_url(re.compile(r".*/checklists/\d+/delete/$"))
        self.page.get_by_role("button", name="Confirm Delete").click()
        expect(self.page).to_have_url(re.compile(r".*/checklists/$"))
        self.assertFalse(Checklist.objects.filter(pk=checklist.pk).exists())

        self.page.goto(f"{self.live_server_url}/shifts/")
        shift_row = self.page.locator("tr", has_text="E2E Shift Delete").first
        shift_row.get_by_role("link", name="Delete").click()
        expect(self.page).to_have_url(re.compile(r".*/shifts/\d+/delete/$"))
        self.page.get_by_role("button", name="Confirm Delete").click()
        expect(self.page).to_have_url(re.compile(r".*/shifts/$"))
        self.assertFalse(Shift.objects.filter(pk=shift.pk).exists())

    def test_manager_can_update_team_shift_alert_preferences_from_settings(self):
        self.staff_user.staff_profile.notify_on_shift_assignment = False
        self.staff_user.staff_profile.save(update_fields=["notify_on_shift_assignment"])
        self._login("e2e_manager", "strong-pass-123")

        self.page.goto(f"{self.live_server_url}/settings/")
        toggle = self.page.locator(f"#notify_staff_{self.staff_user.id}")
        expect(toggle).not_to_be_checked()
        toggle.set_checked(True)
        self.page.get_by_role("button", name="Save Alert Preferences").click()
        expect(self.page).to_have_url(re.compile(r".*/settings/$"))
        expect(self.page.get_by_text("Saved shift alert preferences", exact=False)).to_be_visible()

        self.staff_user.staff_profile.refresh_from_db()
        self.assertTrue(self.staff_user.staff_profile.notify_on_shift_assignment)

    def test_manager_can_update_stock_order_checklist_and_shift_records(self):
        today = timezone.localdate()
        stock_item = StockItem.objects.create(
            name="E2E Update Stock Item",
            category=StockItem.Category.SPIRITS,
            quantity=10,
            unit=StockItem.Unit.BOTTLES,
            minimum_level=4,
            cost="18.00",
            supplier=self.supplier,
            notes="Initial stock notes",
            last_restocked=today,
            is_active=True,
        )
        order = Order.objects.create(
            supplier=self.supplier,
            created_by=self.manager_user,
            order_date=today,
            delivery_date=today + timedelta(days=1),
            status=Order.Status.DRAFT,
            notes="Initial order notes",
        )
        order_item = OrderItem.objects.create(order=order, stock_item=stock_item, quantity=2)
        checklist = Checklist.objects.create(
            title="E2E Update Checklist",
            checklist_type=Checklist.ChecklistType.OPENING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=today,
            completed=False,
            notes="Initial checklist notes",
        )
        shift = Shift.objects.create(
            staff=self.staff_user,
            created_by=self.manager_user,
            shift_date=today,
            start_time=datetime.strptime("09:00", "%H:%M").time(),
            end_time=datetime.strptime("17:00", "%H:%M").time(),
            break_minutes=30,
            notes="Initial shift notes",
        )

        self._login("e2e_manager", "strong-pass-123")

        self.page.goto(f"{self.live_server_url}/stock/{stock_item.pk}/edit/")
        self.page.locator("#id_quantity").fill("14")
        self.page.locator("#id_notes").fill("Updated via E2E smoke")
        self.page.get_by_role("button", name="Save Changes").click()
        expect(self.page).to_have_url(re.compile(r".*/stock/$"))
        stock_item.refresh_from_db()
        self.assertEqual(stock_item.quantity, 14)
        self.assertEqual(stock_item.notes, "Updated via E2E smoke")

        self.page.goto(f"{self.live_server_url}/orders/{order.pk}/edit/")
        self.page.locator("#id_notes").fill("Updated order notes from smoke")
        self.page.locator("#id_items-0-quantity").fill("6")
        self.page.get_by_role("button", name="Save Changes").click()
        expect(self.page).to_have_url(re.compile(r".*/orders/$"))
        order.refresh_from_db()
        order_item.refresh_from_db()
        self.assertEqual(order.notes, "Updated order notes from smoke")
        self.assertEqual(order_item.quantity, 6)

        self.page.goto(f"{self.live_server_url}/orders/")
        order_row = self.page.locator("tr", has_text=order.reference).first
        order_row.locator("select[name='status']").select_option(Order.Status.ORDERED)
        order_row.get_by_role("button", name="Update").click()
        expect(self.page).to_have_url(re.compile(r".*/orders/$"))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ORDERED)

        updated_task_title = "E2E Checklist Updated Title"
        self.page.goto(f"{self.live_server_url}/checklists/{checklist.pk}/edit/")
        self.page.locator("#id_title").fill(updated_task_title)
        self.page.locator("#id_notes").fill("Checklist updated via smoke")
        self.page.get_by_role("button", name="Save Changes").click()
        expect(self.page).to_have_url(re.compile(r".*/checklists/$"))
        checklist.refresh_from_db()
        self.assertEqual(checklist.title, updated_task_title)
        self.assertEqual(checklist.notes, "Checklist updated via smoke")

        checklist_row = self.page.locator("tr", has_text=updated_task_title).first
        checklist_row.get_by_role("button", name="Mark Complete").click()
        expect(self.page).to_have_url(re.compile(r".*/checklists/$"))
        checklist.refresh_from_db()
        self.assertTrue(checklist.completed)

        self.page.goto(f"{self.live_server_url}/shifts/{shift.pk}/edit/")
        self.page.locator("#id_start_time").fill("10:00")
        self.page.locator("#id_end_time").fill("19:00")
        self.page.locator("#id_break_minutes").fill("45")
        self.page.locator("#id_notes").fill("Shift updated via smoke")
        self.page.get_by_role("button", name="Save Changes").click()
        expect(self.page).to_have_url(re.compile(r".*/shifts/$"))
        shift.refresh_from_db()
        self.assertEqual(shift.break_minutes, 45)
        self.assertEqual(shift.notes, "Shift updated via smoke")
