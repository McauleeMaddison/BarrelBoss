from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StaffProfile
from apps.stock.models import StockItem
from apps.suppliers.models import Supplier

from .models import Order, OrderItem


class OrderModelTests(TestCase):
    def test_order_reference_formats_using_primary_key(self):
        manager = User.objects.create_user(username="order_mgr", password="strong-pass-123")
        manager.staff_profile.role = StaffProfile.Role.MANAGER
        manager.staff_profile.save(update_fields=["role"])

        supplier = Supplier.objects.create(name="Brewline")
        order = Order.objects.create(supplier=supplier, created_by=manager)

        self.assertEqual(order.reference, f"ORD-{order.pk:04d}")


class OrderCrudTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="order_staff", password="strong-pass-123")

        self.manager_user = User.objects.create_user(
            username="order_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        self.supplier = Supplier.objects.create(
            name="Cellar Supply Co",
            category_supplied=Supplier.CategorySupplied.BEER_BARRELS,
        )

        self.stock_one = StockItem.objects.create(
            name="Guinness 50L",
            category=StockItem.Category.BEER_BARRELS,
            quantity=8,
            minimum_level=2,
            unit=StockItem.Unit.BARRELS,
            cost=Decimal("114.00"),
        )
        self.stock_two = StockItem.objects.create(
            name="Carling 50L",
            category=StockItem.Category.BEER_BARRELS,
            quantity=4,
            minimum_level=2,
            unit=StockItem.Unit.BARRELS,
            cost=Decimal("99.00"),
        )

    def test_staff_cannot_access_orders(self):
        self.client.login(username="order_staff", password="strong-pass-123")
        response = self.client.get(reverse("orders:list"))
        self.assertRedirects(response, reverse("checklists:list"), fetch_redirect_response=False)

    def test_manager_can_create_order_with_item_lines(self):
        self.client.login(username="order_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("orders:add"),
            {
                "supplier": self.supplier.pk,
                "order_date": "2026-04-22",
                "delivery_date": "2026-04-23",
                "status": Order.Status.ORDERED,
                "notes": "Weekend prep",
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-stock_item": self.stock_one.pk,
                "items-0-quantity": "3",
                "items-1-stock_item": self.stock_two.pk,
                "items-1-quantity": "2",
            },
        )

        self.assertRedirects(response, reverse("orders:list"), fetch_redirect_response=False)
        order = Order.objects.latest("id")
        self.assertEqual(order.supplier, self.supplier)
        self.assertEqual(order.created_by, self.manager_user)
        self.assertEqual(order.items.count(), 2)

    def test_manager_can_update_order_status(self):
        order = Order.objects.create(
            supplier=self.supplier,
            created_by=self.manager_user,
            status=Order.Status.DRAFT,
        )

        self.client.login(username="order_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("orders:status", args=[order.pk]),
            {"status": Order.Status.PENDING_DELIVERY},
        )

        self.assertRedirects(response, reverse("orders:list"), fetch_redirect_response=False)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING_DELIVERY)

    def test_orders_list_filter_by_status(self):
        Order.objects.create(
            supplier=self.supplier,
            created_by=self.manager_user,
            status=Order.Status.PENDING_DELIVERY,
        )
        Order.objects.create(
            supplier=self.supplier,
            created_by=self.manager_user,
            status=Order.Status.DELIVERED,
        )

        self.client.login(username="order_manager", password="strong-pass-123")
        response = self.client.get(reverse("orders:list"), {"status": Order.Status.DELIVERED})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delivered")
        self.assertEqual(response.context["selected_status"], Order.Status.DELIVERED)
        self.assertEqual(response.context["order_count"], 1)

    def test_order_form_requires_at_least_one_item(self):
        self.client.login(username="order_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("orders:add"),
            {
                "supplier": self.supplier.pk,
                "order_date": "2026-04-22",
                "delivery_date": "",
                "status": Order.Status.DRAFT,
                "notes": "No items",
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-stock_item": "",
                "items-0-quantity": "",
                "items-1-stock_item": "",
                "items-1-quantity": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add at least one order item")
        self.assertEqual(Order.objects.count(), 0)
