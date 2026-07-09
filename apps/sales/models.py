from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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

    venue = models.ForeignKey(
        "accounts.Venue",
        on_delete=models.CASCADE,
        related_name="sales_snapshots",
        null=True,
        blank=True,
    )
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
            models.Index(fields=["venue", "business_date"]),
            models.Index(fields=["business_date"]),
            models.Index(fields=["source", "business_date"]),
            models.Index(fields=["location_name", "business_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["venue", "location_name", "source", "business_date"],
                name="uniq_sales_snapshot_venue_location_source_date",
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


class PosIntegration(models.Model):
    class Provider(models.TextChoices):
        TOAST = SalesSnapshot.Source.TOAST, "Toast"
        LIGHTSPEED = SalesSnapshot.Source.LIGHTSPEED, "Lightspeed"
        SQUARE = SalesSnapshot.Source.SQUARE, "Square"
        CLOVER = SalesSnapshot.Source.CLOVER, "Clover"
        OTHER = SalesSnapshot.Source.OTHER, "Other"

    venue = models.ForeignKey(
        "accounts.Venue",
        on_delete=models.CASCADE,
        related_name="pos_integrations",
        null=True,
        blank=True,
    )
    label = models.CharField(max_length=120)
    provider = models.CharField(
        max_length=24,
        choices=Provider.choices,
        default=Provider.TOAST,
    )
    account_identifier = models.CharField(max_length=120, blank=True)
    api_base_url = models.URLField(blank=True)
    webhook_secret = models.CharField(max_length=80, blank=True)
    sync_interval_minutes = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
    )
    is_enabled = models.BooleanField(default=True)
    auto_sync_enabled = models.BooleanField(default=True)
    webhook_enabled = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_integrations_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label", "provider"]
        indexes = [
            models.Index(fields=["venue", "provider", "is_enabled"]),
            models.Index(fields=["provider", "is_enabled"]),
            models.Index(fields=["last_success_at"]),
        ]

    def __str__(self):
        return f"{self.label} ({self.get_provider_display()})"

    @property
    def source_value(self):
        return self.provider

    @property
    def mapped_location_count(self):
        return self.location_mappings.filter(is_active=True).count()

    @property
    def expected_next_sync_at(self):
        anchor = self.last_success_at or self.last_synced_at
        if not (self.is_enabled and self.auto_sync_enabled and anchor):
            return None
        return anchor + timedelta(minutes=self.sync_interval_minutes)

    @property
    def health_state(self):
        if not self.is_enabled:
            return "neutral"
        if self.last_error_at and (
            not self.last_success_at or self.last_error_at >= self.last_success_at
        ):
            return "alert"
        if self.mapped_location_count == 0:
            return "warn"
        if not self.last_success_at:
            return "warn"
        next_sync_at = self.expected_next_sync_at
        if next_sync_at and next_sync_at <= timezone.now():
            return "warn"
        return "ok"

    @property
    def health_label(self):
        if not self.is_enabled:
            return "Paused"
        if self.last_error_at and (
            not self.last_success_at or self.last_error_at >= self.last_success_at
        ):
            return "Connector error"
        if self.mapped_location_count == 0:
            return "Needs mapping"
        if not self.last_success_at:
            return "Awaiting first sync"
        next_sync_at = self.expected_next_sync_at
        if next_sync_at and next_sync_at <= timezone.now():
            return "Sync due"
        return "Healthy"


class PosLocationMapping(models.Model):
    integration = models.ForeignKey(
        PosIntegration,
        on_delete=models.CASCADE,
        related_name="location_mappings",
    )
    external_location_id = models.CharField(max_length=120)
    external_location_name = models.CharField(max_length=120)
    internal_location_name = models.CharField(max_length=120)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    auto_import_enabled = models.BooleanField(default=True)
    latest_business_date = models.DateField(null=True, blank=True)
    latest_net_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["integration__label", "-is_primary", "internal_location_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["integration", "external_location_id"],
                name="uniq_pos_mapping_external_location",
            )
        ]
        indexes = [
            models.Index(fields=["internal_location_name"]),
            models.Index(fields=["is_active", "auto_import_enabled"]),
        ]

    def __str__(self):
        return (
            f"{self.integration.label}: {self.external_location_name} -> "
            f"{self.internal_location_name}"
        )


class PosSyncRun(models.Model):
    class TriggerType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        SCHEDULED = "SCHEDULED", "Scheduled"
        WEBHOOK = "WEBHOOK", "Webhook"

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        PARTIAL = "PARTIAL", "Partial"
        FAILED = "FAILED", "Failed"

    integration = models.ForeignKey(
        PosIntegration,
        on_delete=models.CASCADE,
        related_name="sync_runs",
    )
    business_date = models.DateField(null=True, blank=True)
    trigger_type = models.CharField(
        max_length=16,
        choices=TriggerType.choices,
        default=TriggerType.MANUAL,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_sync_runs_triggered",
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    locations_touched = models.PositiveIntegerField(default=0)
    snapshots_imported = models.PositiveIntegerField(default=0)
    imported_net_sales = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    payload_summary = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["status", "started_at"]),
            models.Index(fields=["integration", "started_at"]),
        ]

    def __str__(self):
        return (
            f"{self.integration.label} {self.get_trigger_type_display()} "
            f"{self.started_at:%Y-%m-%d %H:%M}"
        )

    @property
    def duration_seconds(self):
        if not self.completed_at:
            return 0
        return max(int((self.completed_at - self.started_at).total_seconds()), 0)


class PosWebhookEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        PROCESSED = "PROCESSED", "Processed"
        REJECTED = "REJECTED", "Rejected"
        FAILED = "FAILED", "Failed"

    integration = models.ForeignKey(
        PosIntegration,
        on_delete=models.CASCADE,
        related_name="webhook_events",
    )
    event_type = models.CharField(max_length=120, blank=True)
    external_event_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RECEIVED,
    )
    payload = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        indexes = [
            models.Index(fields=["integration", "received_at"]),
            models.Index(fields=["status", "received_at"]),
        ]

    def __str__(self):
        return (
            f"{self.integration.label} webhook {self.event_type or 'event'} "
            f"{self.received_at:%Y-%m-%d %H:%M}"
        )
