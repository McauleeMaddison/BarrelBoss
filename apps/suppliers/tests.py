from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StaffProfile
from apps.stock.models import StockItem

from .models import Supplier


class SupplierModelTests(TestCase):
    def test_supplier_string_representation(self):
        supplier = Supplier.objects.create(name="Brewline")
        self.assertEqual(str(supplier), "Brewline")


class SupplierAccessTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="supp_staff", password="strong-pass-123")

        self.manager_user = User.objects.create_user(
            username="supp_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

    def test_suppliers_list_requires_management_role(self):
        self.client.login(username="supp_staff", password="strong-pass-123")
        response = self.client.get(reverse("suppliers:list"))
        self.assertRedirects(response, reverse("checklists:list"), fetch_redirect_response=False)

    def test_manager_can_view_suppliers_list(self):
        self.client.login(username="supp_manager", password="strong-pass-123")
        response = self.client.get(reverse("suppliers:list"))
        self.assertEqual(response.status_code, 200)


class SupplierCrudTests(TestCase):
    def setUp(self):
        self.manager_user = User.objects.create_user(
            username="supp_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        self.supplier = Supplier.objects.create(
            name="Brewline",
            contact_name="Siobhan Reed",
            phone="01234567890",
            email="ops@brewline.example",
            category_supplied=Supplier.CategorySupplied.BEER_BARRELS,
        )

    def test_manager_can_create_supplier(self):
        self.client.login(username="supp_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("suppliers:add"),
            {
                "name": "Cellar Supply Co",
                "contact_name": "Ian Finch",
                "phone": "02071222333",
                "email": "orders@cellarsupply.example",
                "category_supplied": Supplier.CategorySupplied.CLEANING,
                "notes": "Preferred for weekly cleaning stock",
            },
        )

        self.assertRedirects(response, reverse("suppliers:list"), fetch_redirect_response=False)
        self.assertTrue(Supplier.objects.filter(name="Cellar Supply Co").exists())

    def test_manager_can_edit_supplier(self):
        self.client.login(username="supp_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("suppliers:edit", args=[self.supplier.pk]),
            {
                "name": self.supplier.name,
                "contact_name": "Updated Contact",
                "phone": self.supplier.phone,
                "email": self.supplier.email,
                "category_supplied": self.supplier.category_supplied,
                "notes": "Updated notes",
            },
        )

        self.assertRedirects(response, reverse("suppliers:list"), fetch_redirect_response=False)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.contact_name, "Updated Contact")

    def test_delete_supplier_sets_stock_supplier_to_null(self):
        item = StockItem.objects.create(
            name="Carling 50L",
            category=StockItem.Category.BEER_BARRELS,
            quantity=3,
            minimum_level=1,
            unit=StockItem.Unit.BARRELS,
            cost="95.00",
            supplier=self.supplier,
        )

        self.client.login(username="supp_manager", password="strong-pass-123")
        response = self.client.post(reverse("suppliers:delete", args=[self.supplier.pk]))

        self.assertRedirects(response, reverse("suppliers:list"), fetch_redirect_response=False)
        self.assertFalse(Supplier.objects.filter(pk=self.supplier.pk).exists())
        item.refresh_from_db()
        self.assertIsNone(item.supplier)

    def test_supplier_list_search_filters_rows(self):
        Supplier.objects.create(
            name="North Wines",
            category_supplied=Supplier.CategorySupplied.WINE,
        )

        self.client.login(username="supp_manager", password="strong-pass-123")
        response = self.client.get(reverse("suppliers:list"), {"q": "brew"})

        self.assertContains(response, "Brewline")
        self.assertNotContains(response, "North Wines")
