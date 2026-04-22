from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

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
