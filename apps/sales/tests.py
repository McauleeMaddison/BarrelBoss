from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffProfile
from apps.shifts.models import Shift
from apps.stock.models import StockItem

from .models import SalesSnapshot


class SalesSnapshotModelTests(TestCase):
    def test_snapshot_calculates_reconciliation_fields(self):
        snapshot = SalesSnapshot(
            net_sales=Decimal("1200.00"),
            cash_sales=Decimal("200.00"),
            card_sales=Decimal("900.00"),
            digital_sales=Decimal("50.00"),
            beer_sales=Decimal("500.00"),
            spirits_sales=Decimal("350.00"),
            wine_sales=Decimal("150.00"),
            soft_sales=Decimal("100.00"),
            food_sales=Decimal("75.00"),
            other_sales=Decimal("25.00"),
            transactions=100,
            covers=80,
        )

        self.assertEqual(snapshot.payment_gap, Decimal("50.00"))
        self.assertEqual(snapshot.category_gap, Decimal("0.00"))
        self.assertEqual(snapshot.avg_ticket, Decimal("12.00"))
        self.assertEqual(snapshot.spend_per_cover, Decimal("15.00"))


class SalesAccessTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="sales_staff",
            password="strong-pass-123",
        )
        self.manager_user = User.objects.create_user(
            username="sales_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

    def test_sales_page_requires_management_access(self):
        self.client.login(username="sales_staff", password="strong-pass-123")
        response = self.client.get(reverse("sales:list"))

        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )

    def test_manager_can_access_sales_page(self):
        self.client.login(username="sales_manager", password="strong-pass-123")
        response = self.client.get(reverse("sales:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Revenue, Payment Mix, and Sync Health")


class SalesListViewTests(TestCase):
    def setUp(self):
        self.manager_user = User.objects.create_user(
            username="sales_view_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        StockItem.objects.create(
            name="Service Lager Keg",
            category=StockItem.Category.BEER_BARRELS,
            quantity=1,
            minimum_level=3,
            unit=StockItem.Unit.BARRELS,
            cost="100.00",
        )
        StockItem.objects.create(
            name="House Gin",
            category=StockItem.Category.SPIRITS,
            quantity=6,
            minimum_level=3,
            unit=StockItem.Unit.BOTTLES,
            cost="22.00",
        )
        Shift.objects.create(
            staff=self.manager_user,
            created_by=self.manager_user,
            shift_date=timezone.localdate(),
            start_time=time(12, 0),
            end_time=time(20, 0),
            break_minutes=30,
            notes="Sales shift",
        )
        SalesSnapshot.objects.create(
            business_date=timezone.localdate(),
            source=SalesSnapshot.Source.TOAST,
            sync_mode=SalesSnapshot.SyncMode.LIVE,
            net_sales="1840.00",
            gross_sales="1910.00",
            discounts="40.00",
            refunds="30.00",
            tips="210.00",
            transactions=142,
            covers=118,
            cash_sales="240.00",
            card_sales="1460.00",
            digital_sales="140.00",
            beer_sales="860.00",
            spirits_sales="420.00",
            wine_sales="180.00",
            soft_sales="170.00",
            food_sales="120.00",
            other_sales="90.00",
            uploaded_by=self.manager_user,
            notes="Primary feed",
        )
        SalesSnapshot.objects.create(
            business_date=timezone.localdate() - timedelta(days=1),
            source=SalesSnapshot.Source.MANUAL,
            sync_mode=SalesSnapshot.SyncMode.MANUAL,
            net_sales="1320.00",
            gross_sales="1370.00",
            discounts="25.00",
            refunds="25.00",
            tips="160.00",
            transactions=104,
            covers=94,
            cash_sales="220.00",
            card_sales="980.00",
            digital_sales="120.00",
            beer_sales="620.00",
            spirits_sales="290.00",
            wine_sales="150.00",
            soft_sales="110.00",
            food_sales="90.00",
            other_sales="60.00",
            uploaded_by=self.manager_user,
            notes="Fallback close",
        )

    def test_sales_list_exposes_premium_metrics(self):
        self.client.login(username="sales_view_manager", password="strong-pass-123")
        response = self.client.get(reverse("sales:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["snapshot_count"], 2)
        self.assertTrue(response.context["attention_items"])
        self.assertEqual(len(response.context["hero_signals"]), 4)
        self.assertEqual(len(response.context["metric_cards"]), 6)
        self.assertContains(response, "Category Revenue Mix")
        self.assertContains(response, "Beer service risk")

    def test_sales_list_filters_by_source(self):
        self.client.login(username="sales_view_manager", password="strong-pass-123")
        response = self.client.get(
            reverse("sales:list"),
            {"source": SalesSnapshot.Source.TOAST, "range": "30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_source"], SalesSnapshot.Source.TOAST)
        self.assertEqual(response.context["snapshot_count"], 1)
        self.assertContains(response, "Toast")

    def test_sales_list_can_export_csv(self):
        self.client.login(username="sales_view_manager", password="strong-pass-123")
        response = self.client.get(reverse("sales:list"), {"export": "csv"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("BarrelBoss Sales Export", response.content.decode("utf-8"))


class SalesCrudViewTests(TestCase):
    def setUp(self):
        self.manager_user = User.objects.create_user(
            username="sales_crud_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

    def test_manager_can_create_sales_snapshot(self):
        self.client.login(username="sales_crud_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("sales:add"),
            {
                "business_date": timezone.localdate().isoformat(),
                "location_name": "Main Bar",
                "source": SalesSnapshot.Source.SQUARE,
                "sync_mode": SalesSnapshot.SyncMode.CSV,
                "external_reference": "SQUARE-1001",
                "gross_sales": "980.00",
                "net_sales": "940.00",
                "discounts": "20.00",
                "refunds": "20.00",
                "tips": "110.00",
                "transactions": 88,
                "covers": 75,
                "cash_sales": "140.00",
                "card_sales": "720.00",
                "digital_sales": "80.00",
                "beer_sales": "410.00",
                "spirits_sales": "180.00",
                "wine_sales": "90.00",
                "soft_sales": "110.00",
                "food_sales": "100.00",
                "other_sales": "50.00",
                "notes": "CSV import closeout",
            },
        )

        self.assertRedirects(response, reverse("sales:list"), fetch_redirect_response=False)
        self.assertTrue(
            SalesSnapshot.objects.filter(
                source=SalesSnapshot.Source.SQUARE,
                external_reference="SQUARE-1001",
            ).exists()
        )
