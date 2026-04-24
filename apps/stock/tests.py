from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StaffProfile
from apps.suppliers.models import Supplier

from .models import StockItem


class StockItemModelTests(TestCase):
    def test_is_low_stock_when_quantity_is_below_or_equal_threshold(self):
        item = StockItem(
            name="Carling 50L",
            category=StockItem.Category.BEER_BARRELS,
            quantity=2,
            unit=StockItem.Unit.BARRELS,
            minimum_level=2,
            cost=Decimal("95.00"),
        )
        self.assertTrue(item.is_low_stock)


class StockListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="stock_user", password="strong-pass-123")
        self.supplier = Supplier.objects.create(
            name="Brewline",
            contact_name="Siobhan Reed",
            category_supplied=Supplier.CategorySupplied.BEER_BARRELS,
        )

        StockItem.objects.create(
            name="Carling 50L",
            category=StockItem.Category.BEER_BARRELS,
            quantity=1,
            minimum_level=2,
            unit=StockItem.Unit.BARRELS,
            cost=Decimal("99.99"),
            supplier=self.supplier,
        )
        StockItem.objects.create(
            name="Jameson",
            category=StockItem.Category.SPIRITS,
            quantity=8,
            minimum_level=3,
            unit=StockItem.Unit.BOTTLES,
            cost=Decimal("24.50"),
        )

    def test_stock_list_requires_login(self):
        response = self.client.get(reverse("stock:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_stock_list_renders_items_from_database(self):
        self.client.login(username="stock_user", password="strong-pass-123")
        response = self.client.get(reverse("stock:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carling 50L")
        self.assertContains(response, "Jameson")
        self.assertEqual(response.context["total_items"], 2)
        self.assertEqual(response.context["low_stock_count"], 1)

    def test_stock_list_filters_by_category(self):
        self.client.login(username="stock_user", password="strong-pass-123")
        response = self.client.get(
            reverse("stock:list"),
            {"category": StockItem.Category.BEER_BARRELS},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carling 50L")
        self.assertNotContains(response, "Jameson")
        self.assertEqual(response.context["selected_category"], StockItem.Category.BEER_BARRELS)

    def test_stock_list_filters_by_urgency(self):
        self.client.login(username="stock_user", password="strong-pass-123")
        response = self.client.get(
            reverse("stock:list"),
            {"urgency": "critical"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carling 50L")
        self.assertNotContains(response, "Jameson")
        self.assertEqual(response.context["selected_urgency"], "critical")

    def test_stock_list_can_export_csv(self):
        self.client.login(username="stock_user", password="strong-pass-123")
        response = self.client.get(
            reverse("stock:list"),
            {"export": "csv"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("BarrelBoss Stock Export", response.content.decode("utf-8"))


class StockCrudViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="stock_staff", password="strong-pass-123")

        self.manager_user = User.objects.create_user(
            username="stock_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        self.supplier = Supplier.objects.create(
            name="Cellar Supply Co",
            category_supplied=Supplier.CategorySupplied.CLEANING,
        )

        self.item = StockItem.objects.create(
            name="Sanitiser",
            category=StockItem.Category.CLEANING,
            quantity=6,
            minimum_level=2,
            unit=StockItem.Unit.UNITS,
            cost=Decimal("8.50"),
            supplier=self.supplier,
        )

    def test_manager_can_create_stock_item(self):
        self.client.login(username="stock_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("stock:add"),
            {
                "name": "Guinness 50L",
                "category": StockItem.Category.BEER_BARRELS,
                "quantity": 4,
                "unit": StockItem.Unit.BARRELS,
                "minimum_level": 2,
                "cost": "104.90",
                "supplier": self.supplier.pk,
                "last_restocked": "2026-04-22",
                "notes": "Priority weekend line",
            },
        )

        self.assertRedirects(response, reverse("stock:list"), fetch_redirect_response=False)
        self.assertTrue(StockItem.objects.filter(name="Guinness 50L", is_active=True).exists())

    def test_staff_cannot_create_stock_item(self):
        self.client.login(username="stock_staff", password="strong-pass-123")
        response = self.client.post(
            reverse("stock:add"),
            {
                "name": "Illegal Add",
                "category": StockItem.Category.SNACKS,
                "quantity": 2,
                "unit": StockItem.Unit.UNITS,
                "minimum_level": 1,
                "cost": "2.99",
                "notes": "Should not be created",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )
        self.assertFalse(StockItem.objects.filter(name="Illegal Add").exists())

    def test_manager_can_edit_stock_item(self):
        self.client.login(username="stock_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("stock:edit", args=[self.item.pk]),
            {
                "name": self.item.name,
                "category": self.item.category,
                "quantity": 12,
                "unit": self.item.unit,
                "minimum_level": self.item.minimum_level,
                "cost": self.item.cost,
                "supplier": self.supplier.pk,
                "last_restocked": "",
                "notes": "Updated level",
            },
        )

        self.assertRedirects(response, reverse("stock:list"), fetch_redirect_response=False)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 12)

    def test_staff_cannot_edit_stock_item(self):
        self.client.login(username="stock_staff", password="strong-pass-123")
        response = self.client.post(
            reverse("stock:edit", args=[self.item.pk]),
            {
                "name": self.item.name,
                "category": self.item.category,
                "quantity": 99,
                "unit": self.item.unit,
                "minimum_level": self.item.minimum_level,
                "cost": self.item.cost,
                "supplier": self.supplier.pk,
                "last_restocked": "",
                "notes": "Attempted staff edit",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )
        self.item.refresh_from_db()
        self.assertNotEqual(self.item.quantity, 99)

    def test_manager_delete_soft_disables_item(self):
        self.client.login(username="stock_manager", password="strong-pass-123")
        response = self.client.post(reverse("stock:delete", args=[self.item.pk]))

        self.assertRedirects(response, reverse("stock:list"), fetch_redirect_response=False)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_active)

    def test_staff_cannot_delete_item(self):
        self.client.login(username="stock_staff", password="strong-pass-123")
        response = self.client.post(reverse("stock:delete", args=[self.item.pk]))

        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_active)
