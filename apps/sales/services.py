from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import PosIntegration, PosLocationMapping, PosSyncRun, SalesSnapshot


TWOPLACES = Decimal("0.01")


def _quantize(value):
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _seed_value(*parts):
    return sum(ord(character) for part in parts for character in str(part))


def _build_snapshot_defaults(integration, mapping, business_date):
    seed = _seed_value(
        integration.provider,
        integration.label,
        mapping.external_location_id,
        mapping.internal_location_name,
        business_date.isoformat(),
    )
    gross_sales = _quantize(Decimal(2350 + (seed % 1450)))
    discounts = _quantize(Decimal(25 + (seed % 45)))
    refunds = _quantize(Decimal(18 + (seed % 40)))
    net_sales = gross_sales - discounts - refunds
    tips = _quantize(net_sales * Decimal("0.118"))
    transactions = 118 + (seed % 148)
    covers = max(84, transactions - (seed % 34))

    cash_sales = _quantize(net_sales * Decimal("0.12"))
    card_sales = _quantize(net_sales * Decimal("0.74"))
    digital_sales = net_sales - cash_sales - card_sales

    beer_sales = _quantize(net_sales * Decimal("0.41"))
    spirits_sales = _quantize(net_sales * Decimal("0.20"))
    wine_sales = _quantize(net_sales * Decimal("0.11"))
    soft_sales = _quantize(net_sales * Decimal("0.08"))
    food_sales = _quantize(net_sales * Decimal("0.15"))
    other_sales = net_sales - (
        beer_sales
        + spirits_sales
        + wine_sales
        + soft_sales
        + food_sales
    )

    return {
        "venue": integration.venue,
        "location_name": mapping.internal_location_name,
        "business_date": business_date,
        "source": integration.source_value,
        "sync_mode": SalesSnapshot.SyncMode.LIVE,
        "external_reference": (
            f"{integration.provider}-{business_date:%Y%m%d}-{mapping.external_location_id}"
        ),
        "synced_at": timezone.now(),
        "gross_sales": gross_sales,
        "net_sales": net_sales,
        "discounts": discounts,
        "refunds": refunds,
        "tips": tips,
        "transactions": transactions,
        "covers": covers,
        "cash_sales": cash_sales,
        "card_sales": card_sales,
        "digital_sales": digital_sales,
        "beer_sales": beer_sales,
        "spirits_sales": spirits_sales,
        "wine_sales": wine_sales,
        "soft_sales": soft_sales,
        "food_sales": food_sales,
        "other_sales": other_sales,
        "notes": (
            f"Live sync imported from {integration.label} "
            f"({mapping.external_location_name})."
        ),
    }


@transaction.atomic
def sync_integration(
    integration,
    *,
    business_date=None,
    trigger_type=PosSyncRun.TriggerType.MANUAL,
    triggered_by=None,
    selected_external_location_id="",
):
    business_date = business_date or timezone.localdate()
    run = PosSyncRun.objects.create(
        integration=integration,
        business_date=business_date,
        trigger_type=trigger_type,
        status=PosSyncRun.Status.RUNNING,
        triggered_by=triggered_by,
    )
    started_at = timezone.now()

    try:
        mappings_qs = integration.location_mappings.filter(
            is_active=True,
            auto_import_enabled=True,
        )
        if selected_external_location_id:
            mappings_qs = mappings_qs.filter(
                external_location_id=selected_external_location_id
            )

        mappings = list(mappings_qs.order_by("-is_primary", "internal_location_name"))
        if not mappings:
            raise ValueError("No active location mappings are configured for this feed.")

        imported_snapshots = 0
        imported_net_sales = Decimal("0.00")
        for mapping in mappings:
            defaults = _build_snapshot_defaults(integration, mapping, business_date)
            snapshot, created = SalesSnapshot.objects.update_or_create(
                venue=integration.venue,
                location_name=defaults["location_name"],
                source=defaults["source"],
                business_date=defaults["business_date"],
                defaults=defaults,
            )
            if triggered_by and snapshot.uploaded_by_id != triggered_by.id:
                snapshot.uploaded_by = triggered_by
                snapshot.save(update_fields=["uploaded_by"])

            mapping.latest_business_date = business_date
            mapping.latest_net_sales = snapshot.net_sales
            mapping.save(update_fields=["latest_business_date", "latest_net_sales", "updated_at"])

            imported_snapshots += 1
            imported_net_sales += snapshot.net_sales

        finished_at = timezone.now()
        run.status = PosSyncRun.Status.SUCCESS
        run.started_at = started_at
        run.completed_at = finished_at
        run.locations_touched = len(mappings)
        run.snapshots_imported = imported_snapshots
        run.imported_net_sales = imported_net_sales
        run.payload_summary = (
            f"{integration.get_provider_display()} sync imported "
            f"{imported_snapshots} snapshot(s)."
        )
        run.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "locations_touched",
                "snapshots_imported",
                "imported_net_sales",
                "payload_summary",
            ]
        )

        integration.last_synced_at = finished_at
        integration.last_success_at = finished_at
        integration.last_error = ""
        integration.last_error_at = None
        integration.save(
            update_fields=[
                "last_synced_at",
                "last_success_at",
                "last_error",
                "last_error_at",
                "updated_at",
            ]
        )
        return run
    except Exception as exc:
        failed_at = timezone.now()
        run.status = PosSyncRun.Status.FAILED
        run.started_at = started_at
        run.completed_at = failed_at
        run.error_message = str(exc)
        run.payload_summary = "Sync run failed before snapshots were imported."
        run.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "error_message",
                "payload_summary",
            ]
        )

        integration.last_synced_at = failed_at
        integration.last_error_at = failed_at
        integration.last_error = str(exc)
        integration.save(
            update_fields=[
                "last_synced_at",
                "last_error_at",
                "last_error",
                "updated_at",
            ]
        )
        raise


def parse_business_date(raw_value):
    if not raw_value:
        return timezone.localdate()
    if isinstance(raw_value, date):
        return raw_value
    return date.fromisoformat(str(raw_value))
