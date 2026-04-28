from datetime import time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.breakages.models import Breakage
from apps.checklists.models import Checklist
from apps.orders.models import Order, OrderItem
from apps.shifts.models import Shift
from apps.stock.models import StockItem
from apps.suppliers.models import Supplier


class Command(BaseCommand):
    help = "Create a realistic demo dataset for client preview walkthroughs."
    demo_tag = "[DEMO_PREVIEW]"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="strong-pass-123",
            help="Password applied when bootstrapping demo accounts (default: strong-pass-123).",
        )
        parser.add_argument(
            "--append",
            action="store_true",
            help="Append data instead of replacing previous demo preview records.",
        )

    def _demo_users(self):
        user_model = get_user_model()
        try:
            return {
                "landlord": user_model.objects.get(username="landlord"),
                "manager": user_model.objects.get(username="manager"),
                "staff": user_model.objects.get(username="staff"),
            }
        except user_model.DoesNotExist as exc:
            raise CommandError(
                "Demo users are missing. Run bootstrap_demo_accounts first."
            ) from exc

    def _delete_existing_demo_records(self):
        deleted = {}
        deleted["orders"], _ = Order.objects.filter(notes__contains=self.demo_tag).delete()
        deleted["checklists"], _ = Checklist.objects.filter(
            notes__contains=self.demo_tag
        ).delete()
        deleted["shifts"], _ = Shift.objects.filter(notes__contains=self.demo_tag).delete()
        deleted["breakages"], _ = Breakage.objects.filter(
            notes__contains=self.demo_tag
        ).delete()
        deleted["stock"], _ = StockItem.objects.filter(notes__contains=self.demo_tag).delete()
        deleted["suppliers"], _ = Supplier.objects.filter(
            notes__contains=self.demo_tag
        ).delete()
        return deleted

    def _create_suppliers(self):
        suppliers = {}
        rows = [
            {
                "name": "Northern Ales Wholesale",
                "contact_name": "Paula Green",
                "phone": "0161 555 1201",
                "email": "orders@northernales.example",
                "category_supplied": Supplier.CategorySupplied.BEER_BARRELS,
            },
            {
                "name": "City Spirits Co.",
                "contact_name": "Nathan Cole",
                "phone": "0207 555 7788",
                "email": "trade@cityspirits.example",
                "category_supplied": Supplier.CategorySupplied.SPIRITS,
            },
            {
                "name": "FreshFizz Distribution",
                "contact_name": "Aria Patel",
                "phone": "0113 555 4488",
                "email": "ops@freshfizz.example",
                "category_supplied": Supplier.CategorySupplied.SOFT_DRINKS,
            },
            {
                "name": "CellarCare Supplies",
                "contact_name": "Imran Shah",
                "phone": "0121 555 6677",
                "email": "support@cellarcare.example",
                "category_supplied": Supplier.CategorySupplied.CLEANING,
            },
        ]

        for row in rows:
            supplier = Supplier.objects.create(
                **row,
                notes=f"{self.demo_tag} Supplier seeded for showcase previews.",
            )
            suppliers[supplier.name] = supplier
        return suppliers

    def _create_stock(self, suppliers, today):
        stock_by_name = {}
        rows = [
            (
                "Amstel Keg 50L",
                StockItem.Category.BEER_BARRELS,
                4,
                StockItem.Unit.BARRELS,
                6,
                "119.00",
                "Northern Ales Wholesale",
            ),
            (
                "Guinness Keg 50L",
                StockItem.Category.BEER_BARRELS,
                2,
                StockItem.Unit.BARRELS,
                5,
                "134.00",
                "Northern Ales Wholesale",
            ),
            (
                "House Red Wine",
                StockItem.Category.WINE,
                28,
                StockItem.Unit.BOTTLES,
                12,
                "8.90",
                "City Spirits Co.",
            ),
            (
                "Premium Gin 70cl",
                StockItem.Category.SPIRITS,
                16,
                StockItem.Unit.BOTTLES,
                8,
                "19.50",
                "City Spirits Co.",
            ),
            (
                "Tonic Water 24x200ml",
                StockItem.Category.MIXERS,
                5,
                StockItem.Unit.BOXES,
                7,
                "11.40",
                "FreshFizz Distribution",
            ),
            (
                "Cola 330ml",
                StockItem.Category.SOFT_DRINKS,
                42,
                StockItem.Unit.CANS,
                18,
                "0.82",
                "FreshFizz Distribution",
            ),
            (
                "Lime Juice",
                StockItem.Category.GARNISHES,
                10,
                StockItem.Unit.BOTTLES,
                6,
                "3.10",
                "FreshFizz Distribution",
            ),
            (
                "Pint Glasses",
                StockItem.Category.GLASSWARE,
                72,
                StockItem.Unit.UNITS,
                40,
                "2.60",
                "CellarCare Supplies",
            ),
            (
                "Sanitiser Solution 5L",
                StockItem.Category.CLEANING,
                6,
                StockItem.Unit.UNITS,
                4,
                "14.20",
                "CellarCare Supplies",
            ),
        ]

        for idx, row in enumerate(rows):
            (
                name,
                category,
                quantity,
                unit,
                minimum_level,
                cost,
                supplier_name,
            ) = row
            stock_item = StockItem.objects.create(
                name=name,
                category=category,
                quantity=quantity,
                unit=unit,
                minimum_level=minimum_level,
                cost=cost,
                supplier=suppliers[supplier_name],
                last_restocked=today - timedelta(days=(idx % 5) + 1),
                notes=f"{self.demo_tag} Stock profile for client preview.",
                is_active=True,
            )
            stock_by_name[name] = stock_item
        return stock_by_name

    def _create_orders(self, users, suppliers, stock_by_name, today):
        manager_user = users["manager"]
        order_rows = [
            {
                "supplier": suppliers["Northern Ales Wholesale"],
                "status": Order.Status.ORDERED,
                "order_date": today - timedelta(days=2),
                "delivery_date": today + timedelta(days=1),
                "items": [("Amstel Keg 50L", 4), ("Guinness Keg 50L", 3)],
            },
            {
                "supplier": suppliers["City Spirits Co."],
                "status": Order.Status.PENDING_DELIVERY,
                "order_date": today - timedelta(days=1),
                "delivery_date": today + timedelta(days=2),
                "items": [("Premium Gin 70cl", 8), ("House Red Wine", 12)],
            },
            {
                "supplier": suppliers["FreshFizz Distribution"],
                "status": Order.Status.DRAFT,
                "order_date": today,
                "delivery_date": today + timedelta(days=3),
                "items": [("Tonic Water 24x200ml", 10), ("Cola 330ml", 25)],
            },
            {
                "supplier": suppliers["CellarCare Supplies"],
                "status": Order.Status.DELIVERED,
                "order_date": today - timedelta(days=4),
                "delivery_date": today - timedelta(days=1),
                "items": [("Sanitiser Solution 5L", 4), ("Pint Glasses", 36)],
            },
        ]

        orders = []
        for row in order_rows:
            order = Order.objects.create(
                supplier=row["supplier"],
                created_by=manager_user,
                order_date=row["order_date"],
                delivery_date=row["delivery_date"],
                status=row["status"],
                notes=f"{self.demo_tag} Showcase order lifecycle sample.",
            )
            for stock_name, quantity in row["items"]:
                OrderItem.objects.create(
                    order=order,
                    stock_item=stock_by_name[stock_name],
                    quantity=quantity,
                )
            orders.append(order)
        return orders

    def _create_checklists(self, users, today):
        staff_user = users["staff"]
        manager_user = users["manager"]
        checklist_rows = [
            (
                "Open cellar and line clean",
                Checklist.ChecklistType.OPENING,
                today,
                False,
            ),
            (
                "Verify spirit counts against till close",
                Checklist.ChecklistType.CLOSING,
                today + timedelta(days=1),
                False,
            ),
            (
                "Confirm keg delivery checklist",
                Checklist.ChecklistType.DELIVERY,
                today - timedelta(days=1),
                True,
            ),
            (
                "Deep clean bar tops and taps",
                Checklist.ChecklistType.CLEANING,
                today + timedelta(days=2),
                False,
            ),
        ]

        checklists = []
        for title, checklist_type, due_date, completed in checklist_rows:
            checklist = Checklist.objects.create(
                title=title,
                checklist_type=checklist_type,
                assigned_to=staff_user,
                created_by=manager_user,
                due_date=due_date,
                completed=completed,
                notes=f"{self.demo_tag} Operational discipline sample.",
            )
            if completed:
                checklist.completed_at = timezone.now()
                checklist.save(update_fields=["completed_at"])
            checklists.append(checklist)
        return checklists

    def _create_shifts(self, users, today):
        staff_user = users["staff"]
        manager_user = users["manager"]
        shifts = []
        shift_rows = [
            (today, time(10, 0), time(18, 0), 30, "Main floor lunch + early evening"),
            (
                today + timedelta(days=1),
                time(14, 0),
                time(22, 30),
                45,
                "Late shift with cocktail focus",
            ),
            (
                today + timedelta(days=3),
                time(16, 0),
                time(23, 0),
                30,
                "Sports night coverage",
            ),
        ]

        for shift_date, start_time, end_time, break_minutes, note in shift_rows:
            shifts.append(
                Shift.objects.create(
                    staff=staff_user,
                    created_by=manager_user,
                    shift_date=shift_date,
                    start_time=start_time,
                    end_time=end_time,
                    break_minutes=break_minutes,
                    notes=f"{self.demo_tag} {note}",
                )
            )
        return shifts

    def _create_breakages(self, users):
        staff_user = users["staff"]
        rows = [
            ("Pint Glass", 3, Breakage.IssueType.BROKEN, "Busy Saturday spill"),
            ("Wine Glass", 2, Breakage.IssueType.DAMAGED, "Chipped rim found in wash"),
            ("Whiskey Tumbler", 1, Breakage.IssueType.REPLACEMENT_NEEDED, "Cracked base"),
        ]
        breakages = []
        for item_name, quantity, issue_type, note in rows:
            breakages.append(
                Breakage.objects.create(
                    item_name=item_name,
                    quantity=quantity,
                    issue_type=issue_type,
                    reported_by=staff_user,
                    notes=f"{self.demo_tag} {note}",
                )
            )
        return breakages

    def handle(self, *args, **options):
        if not getattr(settings, "ALLOW_DEMO_ACCOUNT_BOOTSTRAP", False):
            raise CommandError(
                "Demo data bootstrap is disabled. Set ALLOW_DEMO_ACCOUNT_BOOTSTRAP=true to enable."
            )

        password = options["password"]
        append_mode = options["append"]

        call_command("bootstrap_demo_accounts", password=password, stdout=self.stdout)
        users = self._demo_users()
        today = timezone.localdate()

        with transaction.atomic():
            if append_mode:
                deleted = {
                    "orders": 0,
                    "checklists": 0,
                    "shifts": 0,
                    "breakages": 0,
                    "stock": 0,
                    "suppliers": 0,
                }
            else:
                deleted = self._delete_existing_demo_records()

            suppliers = self._create_suppliers()
            stock_by_name = self._create_stock(suppliers, today)
            orders = self._create_orders(users, suppliers, stock_by_name, today)
            checklists = self._create_checklists(users, today)
            shifts = self._create_shifts(users, today)
            breakages = self._create_breakages(users)

        self.stdout.write(self.style.SUCCESS("Demo preview dataset ready."))
        self.stdout.write(f" - suppliers: {len(suppliers)}")
        self.stdout.write(f" - stock items: {len(stock_by_name)}")
        self.stdout.write(f" - orders: {len(orders)}")
        self.stdout.write(f" - checklists: {len(checklists)}")
        self.stdout.write(f" - shifts: {len(shifts)}")
        self.stdout.write(f" - breakages: {len(breakages)}")
        if not append_mode:
            self.stdout.write(
                " - replaced existing demo records: "
                f"orders={deleted['orders']}, "
                f"checklists={deleted['checklists']}, "
                f"shifts={deleted['shifts']}, "
                f"breakages={deleted['breakages']}, "
                f"stock={deleted['stock']}, "
                f"suppliers={deleted['suppliers']}"
            )
