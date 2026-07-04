from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class SalesSnapshot(models.Model):
    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual Till Close"
        TOAST = "TOAST", "Toast"
        LIGHTSPEED = "LIGHTSPEED", "Lightspeed"
        SQUARE = "SQUARE", "Square"
        CLOVER = "CLOVER", "Clover"
        OTHER = "OTHER", "Other"

    class SyncMode(models.TextChoices):
        MANUAL = "MANUAL", "Manual Entry"
        CSV = "CSV", "CSV Import"
        LIVE = "LIVE", "Live Sync"

    location_name = models.CharField(max_length=120, default="Main Bar")
    business_date = models.DateField(default=timezone.localdate)
    source = models.CharField(
        max_length=24,
        choices=Source.choices,
        default=Source.MANUAL,
    )
    sync_mode = models.CharField(
        max_length=16,
        choices=SyncMode.choices,
        default=SyncMode.MANUAL,
    )
    external_reference = models.CharField(max_length=120, blank=True)
    synced_at = models.DateTimeField(default=timezone.now)
    gross_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    net_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    discounts = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    refunds = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    tips = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    transactions = models.PositiveIntegerField(default=0)
    covers = models.PositiveIntegerField(default=0)
    cash_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    card_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    digital_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    beer_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    spirits_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    wine_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    soft_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    food_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    other_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_snapshots_uploaded",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-business_date", "-synced_at", "-id"]
        indexes = [
            models.Index(fields=["business_date"]),
            models.Index(fields=["source", "business_date"]),
            models.Index(fields=["location_name", "business_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["location_name", "source", "business_date"],
                name="uniq_sales_snapshot_location_source_date",
            )
        ]

    def __str__(self):
        return (
            f"{self.location_name} {self.business_date:%Y-%m-%d} "
            f"{self.get_source_display()} £{self.net_sales}"
        )

    @property
    def payment_total(self):
        return self.cash_sales + self.card_sales + self.digital_sales

    @property
    def category_total(self):
        return (
            self.beer_sales
            + self.spirits_sales
            + self.wine_sales
            + self.soft_sales
            + self.food_sales
            + self.other_sales
        )

    @property
    def payment_gap(self):
        return self.net_sales - self.payment_total

    @property
    def category_gap(self):
        return self.net_sales - self.category_total

    @property
    def avg_ticket(self):
        if not self.transactions:
            return Decimal("0.00")
        return self.net_sales / Decimal(self.transactions)

    @property
    def spend_per_cover(self):
        if not self.covers:
            return Decimal("0.00")
        return self.net_sales / Decimal(self.covers)

