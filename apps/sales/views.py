import csv
import json
import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.accounts.permissions import management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from apps.shifts.models import Shift
from apps.stock.models import StockItem
from taptrack.pagination import build_query_string, paginate_collection

from .forms import PosIntegrationForm, PosLocationMappingForm, SalesSnapshotForm
from .models import (
    PosIntegration,
    PosLocationMapping,
    PosSyncRun,
    PosWebhookEvent,
    SalesSnapshot,
)
from .services import parse_business_date, sync_integration


def _sum_shift_hours_for_range(start_date, end_date):
    shifts = Shift.objects.filter(shift_date__range=(start_date, end_date))
    return round(sum(shift.duration_hours for shift in shifts), 1)


def _rate(part, whole):
    if not whole:
        return 0
    return round((part / whole) * 100, 1)


def _currency(value):
    return f"£{value:,.2f}"


def _integration_queryset():
    return (
        PosIntegration.objects.annotate(
            active_mapping_count=Count(
                "location_mappings",
                filter=Q(location_mappings__is_active=True),
                distinct=True,
            )
        )
        .prefetch_related("location_mappings", "sync_runs")
        .order_by("label", "provider")
    )


def _expected_next_sync_at(integration):
    anchor = integration.last_success_at or integration.last_synced_at
    if not (integration.is_enabled and integration.auto_sync_enabled and anchor):
        return None
    return anchor + timedelta(minutes=integration.sync_interval_minutes)


def _integration_health_state(integration):
    mapped_count = getattr(integration, "active_mapping_count", 0)
    if not integration.is_enabled:
        return "neutral"
    if integration.last_error_at and (
        not integration.last_success_at or integration.last_error_at >= integration.last_success_at
    ):
        return "alert"
    if mapped_count == 0:
        return "warn"
    if not integration.last_success_at:
        return "warn"
    next_sync_at = _expected_next_sync_at(integration)
    if next_sync_at and next_sync_at <= timezone.now():
        return "warn"
    return "ok"


def _integration_health_label(integration):
    mapped_count = getattr(integration, "active_mapping_count", 0)
    if not integration.is_enabled:
        return "Paused"
    if integration.last_error_at and (
        not integration.last_success_at or integration.last_error_at >= integration.last_success_at
    ):
        return "Connector error"
    if mapped_count == 0:
        return "Needs mapping"
    if not integration.last_success_at:
        return "Awaiting first sync"
    next_sync_at = _expected_next_sync_at(integration)
    if next_sync_at and next_sync_at <= timezone.now():
        return "Sync due"
    return "Healthy"


def _format_sync_moment(moment):
    if not moment:
        return "Never"
    return timezone.localtime(moment).strftime("%d %b · %H:%M")


def _build_sync_center_rows(request, integrations):
    connector_rows = []
    for integration in integrations:
        state = _integration_health_state(integration)
        next_sync_at = _expected_next_sync_at(integration)
        mappings = [
            mapping
            for mapping in integration.location_mappings.all()
            if mapping.is_active
        ]
        latest_run = next(iter(integration.sync_runs.all()), None)
        connector_rows.append(
            {
                "integration": integration,
                "provider": integration.get_provider_display(),
                "state": _integration_health_label(integration),
                "state_tone": state,
                "mapping_count": len(mappings),
                "meta": (
                    f"{len(mappings)} mapped location(s) · every "
                    f"{integration.sync_interval_minutes} minute(s)"
                ),
                "detail": (
                    integration.last_error
                    if state == "alert" and integration.last_error
                    else (
                        f"Next sync target {next_sync_at.strftime('%H:%M')}"
                        if next_sync_at
                        else "Manual sync control"
                    )
                ),
                "last_success": _format_sync_moment(integration.last_success_at),
                "last_sync": _format_sync_moment(integration.last_synced_at),
                "latest_run": latest_run,
                "webhook_url": request.build_absolute_uri(
                    reverse("sales:webhook", args=[integration.pk])
                ),
                "secret_preview": (
                    f"{integration.webhook_secret[:4]}••••{integration.webhook_secret[-4:]}"
                    if integration.webhook_secret
                    else "Not set"
                ),
                "mappings": mappings[:3],
            }
        )
    return connector_rows


def _build_sales_attention_items(
    *,
    integrations,
    latest_snapshot,
    today_snapshot,
    refund_rate,
    stock_risks,
):
    attention_items = []
    connector_issues = [
        integration for integration in integrations if _integration_health_state(integration) != "ok"
    ]

    if not integrations:
        attention_items.append(
            {
                "label": "POS feeds",
                "value": "Not connected",
                "copy": "No Toast, Lightspeed, Square, or Clover feed is configured yet.",
                "tone": "alert",
                "action_label": "Open sync center",
                "url_name": "sales:sync_center",
            }
        )
    elif connector_issues:
        attention_items.append(
            {
                "label": "Connector health",
                "value": f"{len(connector_issues)} need attention",
                "copy": "At least one feed is due, errored, or missing location mapping.",
                "tone": "warn",
                "action_label": "Review feeds",
                "url_name": "sales:sync_center",
            }
        )

    if latest_snapshot is None or latest_snapshot.business_date < timezone.localdate():
        attention_items.append(
            {
                "label": "Sync freshness",
                "value": "Needs sync",
                "copy": "No live sales snapshot has landed for today yet. Log a till close or reconnect the POS feed.",
                "tone": "alert",
                "action_label": "Log snapshot",
                "url_name": "sales:add",
            }
        )

    if today_snapshot and abs(today_snapshot.payment_gap) >= Decimal("15.00"):
        attention_items.append(
            {
                "label": "Payment gap",
                "value": _currency(abs(today_snapshot.payment_gap)),
                "copy": "Payment mix does not reconcile cleanly against net sales. Check till close totals and tender mapping.",
                "tone": "warn",
                "action_label": "Review sales",
                "url_name": "sales:list",
            }
        )

    if refund_rate >= 3:
        attention_items.append(
            {
                "label": "Refund pressure",
                "value": f"{refund_rate:.1f}%",
                "copy": "Refunds are elevated for the selected period and should be reviewed before close.",
                "tone": "warn",
                "action_label": "Review snapshots",
                "url_name": "sales:list",
            }
        )

    if today_snapshot and today_snapshot.beer_sales > 0 and stock_risks["beer"] > 0:
        attention_items.append(
            {
                "label": "Beer service risk",
                "value": f"{stock_risks['beer']} low line(s)",
                "copy": "Beer sales are still flowing while live stock lines in beer barrels are already below minimum.",
                "tone": "alert",
                "action_label": "Open stock",
                "url_name": "stock:list",
                "query": "urgency=critical",
            }
        )

    if not attention_items:
        attention_items.append(
            {
                "label": "Sales board",
                "value": "Healthy",
                "copy": "Revenue, payment reconciliation, and connector freshness are currently under control.",
                "tone": "ok",
                "action_label": "Open sync center",
                "url_name": "sales:sync_center",
            }
        )

    return attention_items


def _build_sync_summary(integrations):
    active_connector_count = sum(1 for integration in integrations if integration.is_enabled)
    mapped_location_count = sum(
        getattr(integration, "active_mapping_count", 0) for integration in integrations
    )
    connectors_needing_attention = sum(
        1 for integration in integrations if _integration_health_state(integration) != "ok"
    )
    webhook_queue_count = PosWebhookEvent.objects.filter(
        status=PosWebhookEvent.Status.RECEIVED
    ).count()
    return {
        "active_connector_count": active_connector_count,
        "mapped_location_count": mapped_location_count,
        "connectors_needing_attention": connectors_needing_attention,
        "webhook_queue_count": webhook_queue_count,
    }


@management_required
def list_sales(request):
    selected_source = request.GET.get("source", "")
    selected_range = request.GET.get("range", "30")
    query = (request.GET.get("q") or "").strip()
    allowed_ranges = {"7": 7, "30": 30, "90": 90}
    if selected_range not in allowed_ranges:
        selected_range = "30"

    today = timezone.localdate()
    range_start = today - timedelta(days=allowed_ranges[selected_range] - 1)
    snapshots_qs = SalesSnapshot.objects.select_related("uploaded_by")
    integrations = list(_integration_queryset())

    if selected_source and selected_source in SalesSnapshot.Source.values:
        snapshots_qs = snapshots_qs.filter(source=selected_source)

    if query:
        snapshots_qs = snapshots_qs.filter(
            Q(location_name__icontains=query)
            | Q(external_reference__icontains=query)
            | Q(notes__icontains=query)
        )

    display_qs = snapshots_qs.filter(business_date__gte=range_start).order_by(
        "-business_date", "-synced_at", "-id"
    )
    page_obj = paginate_collection(request, display_qs, per_page=12)
    snapshots = list(page_obj.object_list)

    totals = display_qs.aggregate(
        gross_sales=Sum("gross_sales"),
        net_sales=Sum("net_sales"),
        discounts=Sum("discounts"),
        refunds=Sum("refunds"),
        tips=Sum("tips"),
        transactions=Sum("transactions"),
        covers=Sum("covers"),
        cash_sales=Sum("cash_sales"),
        card_sales=Sum("card_sales"),
        digital_sales=Sum("digital_sales"),
        beer_sales=Sum("beer_sales"),
        spirits_sales=Sum("spirits_sales"),
        wine_sales=Sum("wine_sales"),
        soft_sales=Sum("soft_sales"),
        food_sales=Sum("food_sales"),
        other_sales=Sum("other_sales"),
    )
    total_gross_sales = totals["gross_sales"] or Decimal("0.00")
    total_net_sales = totals["net_sales"] or Decimal("0.00")
    total_refunds = totals["refunds"] or Decimal("0.00")
    total_transactions = totals["transactions"] or 0
    total_covers = totals["covers"] or 0
    total_cash_sales = totals["cash_sales"] or Decimal("0.00")
    total_card_sales = totals["card_sales"] or Decimal("0.00")
    total_digital_sales = totals["digital_sales"] or Decimal("0.00")

    total_labor_hours = _sum_shift_hours_for_range(range_start, today)
    refund_rate = _rate(total_refunds, total_gross_sales)
    sales_per_labor_hour = (
        round(total_net_sales / Decimal(str(total_labor_hours)), 2)
        if total_labor_hours
        else Decimal("0.00")
    )
    average_ticket = (
        total_net_sales / Decimal(total_transactions)
        if total_transactions
        else Decimal("0.00")
    )
    spend_per_cover = (
        total_net_sales / Decimal(total_covers)
        if total_covers
        else Decimal("0.00")
    )

    latest_snapshot = snapshots_qs.order_by("-business_date", "-synced_at", "-id").first()
    today_snapshot = snapshots_qs.filter(business_date=today).order_by(
        "-synced_at", "-id"
    ).first()
    today_labor_hours = _sum_shift_hours_for_range(today, today)

    stock_risks = {
        "beer": StockItem.objects.filter(
            is_active=True,
            category=StockItem.Category.BEER_BARRELS,
            quantity__lte=F("minimum_level"),
        ).count(),
        "spirits": StockItem.objects.filter(
            is_active=True,
            category=StockItem.Category.SPIRITS,
            quantity__lte=F("minimum_level"),
        ).count(),
        "wine": StockItem.objects.filter(
            is_active=True,
            category=StockItem.Category.WINE,
            quantity__lte=F("minimum_level"),
        ).count(),
        "soft": StockItem.objects.filter(
            is_active=True,
            category__in=[StockItem.Category.SOFT_DRINKS, StockItem.Category.MIXERS],
            quantity__lte=F("minimum_level"),
        ).count(),
    }
    total_stock_risk_lines = sum(stock_risks.values())

    sync_summary = _build_sync_summary(integrations)
    attention_items = _build_sales_attention_items(
        integrations=integrations,
        latest_snapshot=latest_snapshot,
        today_snapshot=today_snapshot,
        refund_rate=refund_rate,
        stock_risks=stock_risks,
    )

    hero_signals = [
        {
            "label": "Live sync status",
            "value": (
                "Live today"
                if today_snapshot and today_snapshot.sync_mode == SalesSnapshot.SyncMode.LIVE
                else (
                    f"Last close {latest_snapshot.business_date:%d %b}"
                    if latest_snapshot
                    else "No snapshots"
                )
            ),
            "copy": (
                f"{latest_snapshot.get_source_display()} via {latest_snapshot.get_sync_mode_display()}."
                if latest_snapshot
                else "Connect a POS feed or log the first daily snapshot."
            ),
            "tone": "ok"
            if today_snapshot and today_snapshot.sync_mode == SalesSnapshot.SyncMode.LIVE
            else "warn",
        },
        {
            "label": "Active connectors",
            "value": sync_summary["active_connector_count"],
            "copy": (
                f"{sync_summary['connectors_needing_attention']} connector(s) need attention."
                if sync_summary["connectors_needing_attention"]
                else "All configured feeds are healthy or ready for their next sync."
            ),
            "tone": "ok"
            if sync_summary["active_connector_count"] and not sync_summary["connectors_needing_attention"]
            else "warn",
        },
        {
            "label": "Mapped locations",
            "value": sync_summary["mapped_location_count"],
            "copy": "Each mapped location feeds the internal venue close-out board.",
            "tone": "neutral",
        },
        {
            "label": "Webhook queue",
            "value": sync_summary["webhook_queue_count"],
            "copy": (
                "Inbound events are waiting to be processed."
                if sync_summary["webhook_queue_count"]
                else "Webhook intake is currently clear."
            ),
            "tone": "warn" if sync_summary["webhook_queue_count"] else "ok",
        },
    ]

    metric_cards = [
        {
            "label": "Net Sales In View",
            "value": _currency(total_net_sales),
            "state": f"{allowed_ranges[selected_range]} day window",
            "state_tone": "ok",
            "summary": f"{display_qs.count()} synced day(s) are included in the current view.",
            "note": "Use this as the live revenue pulse for the selected window and source mix.",
            "actions": [
                {"label": "Open sync center", "url_name": "sales:sync_center"},
            ],
            "tone": "ok",
        },
        {
            "label": "Average Ticket",
            "value": _currency(average_ticket),
            "state": f"{total_transactions} transaction(s)",
            "state_tone": "neutral",
            "summary": (
                f"{total_covers} covers recorded with {_currency(spend_per_cover)} average spend per cover."
                if total_covers
                else "No covers have been logged in the current view yet."
            ),
            "note": "Ticket size is the fastest proxy for service mix and upsell quality.",
            "actions": [
                {"label": "Review snapshots", "url_name": "sales:list"},
            ],
            "tone": "neutral",
        },
        {
            "label": "Sales Per Labor Hour",
            "value": _currency(sales_per_labor_hour),
            "state": f"{total_labor_hours} labor hour(s)",
            "state_tone": "ok" if total_labor_hours else "warn",
            "summary": (
                f"{_currency(total_net_sales)} against {total_labor_hours} scheduled labor hour(s)."
                if total_labor_hours
                else "Schedule hours to unlock labor efficiency benchmarking."
            ),
            "note": "This is the live hand-off from revenue into rota planning and labor control.",
            "actions": [
                {"label": "Open roster", "url_name": "shifts:list"},
            ],
            "tone": "ok",
        },
        {
            "label": "Refund Rate",
            "value": f"{refund_rate:.1f}%",
            "state": _currency(total_refunds),
            "state_tone": "warn" if refund_rate >= 3 else "ok",
            "summary": "Refunds and void-like leakage should stay tight against gross sales.",
            "note": "Elevated refund rates usually deserve a manager close-out review.",
            "actions": [
                {"label": "Review close quality", "url_name": "sales:list"},
            ],
            "tone": "warn",
        },
    ]

    category_fields = [
        ("Beer", totals["beer_sales"] or Decimal("0.00"), stock_risks["beer"]),
        ("Spirits", totals["spirits_sales"] or Decimal("0.00"), stock_risks["spirits"]),
        ("Wine", totals["wine_sales"] or Decimal("0.00"), stock_risks["wine"]),
        ("Soft & Mixers", totals["soft_sales"] or Decimal("0.00"), stock_risks["soft"]),
        ("Food", totals["food_sales"] or Decimal("0.00"), 0),
        ("Other", totals["other_sales"] or Decimal("0.00"), 0),
    ]
    margin_mix = []
    for label, value, risk_lines in category_fields:
        margin_mix.append(
            {
                "label": label,
                "value": _currency(value),
                "share": f"{_rate(value, total_net_sales):.1f}%",
                "meta": (
                    f"{risk_lines} low stock line(s)"
                    if risk_lines
                    else "No direct stock pressure flagged"
                ),
            }
        )

    ops_handoff = [
        {
            "label": "Card / digital mix",
            "value": f"{_rate(total_card_sales + total_digital_sales, total_net_sales):.1f}%",
            "meta": "Primary modern tender share across the selected period.",
        },
        {
            "label": "Cash handling",
            "value": _currency(total_cash_sales),
            "meta": "Use this against till-close cashing-up and reconciliation.",
        },
        {
            "label": "Tips captured",
            "value": _currency(totals["tips"] or Decimal("0.00")),
            "meta": "Foundation for tip pooling and payroll export next.",
        },
        {
            "label": "Service lines at risk",
            "value": total_stock_risk_lines,
            "meta": "Low-stock beverage lines currently under live trading pressure.",
        },
    ]

    connector_rows = _build_sync_center_rows(request, integrations)

    for snapshot in snapshots:
        snapshot.payment_gap_display = _currency(abs(snapshot.payment_gap))
        snapshot.payment_gap_badge_class = (
            "badge-status-pending"
            if abs(snapshot.payment_gap) >= Decimal("15.00")
            else "badge-stock-healthy"
        )
        snapshot.sales_per_labor_hour = Decimal("0.00")
        day_labor_hours = _sum_shift_hours_for_range(snapshot.business_date, snapshot.business_date)
        if day_labor_hours:
            snapshot.sales_per_labor_hour = round(
                snapshot.net_sales / Decimal(str(day_labor_hours)),
                2,
            )
        snapshot.sync_badge_class = (
            "badge-stock-healthy"
            if snapshot.sync_mode == SalesSnapshot.SyncMode.LIVE
            else "badge-status-pending"
        )

    filters_active = bool(query or selected_source or selected_range != "30")
    filter_presets = [
        {
            "label": "Last 7 Days",
            "query": "range=7",
            "active": selected_range == "7" and not selected_source and not query,
        },
        {
            "label": "Last 30 Days",
            "query": "range=30",
            "active": selected_range == "30" and not selected_source and not query,
        },
        {
            "label": "Last 90 Days",
            "query": "range=90",
            "active": selected_range == "90" and not selected_source and not query,
        },
        {
            "label": "Toast Feed",
            "query": f"range={selected_range}&source={SalesSnapshot.Source.TOAST}",
            "active": selected_source == SalesSnapshot.Source.TOAST and not query,
        },
    ]

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="barrelboss-sales.csv"'
        writer = csv.writer(response)
        writer.writerow(["BarrelBoss Sales Export"])
        writer.writerow(
            [
                "Business Date",
                "Location",
                "Source",
                "Sync Mode",
                "Net Sales",
                "Gross Sales",
                "Refunds",
                "Transactions",
                "Covers",
                "Cash",
                "Card",
                "Digital",
                "Beer",
                "Spirits",
                "Wine",
                "Soft",
                "Food",
                "Other",
                "Reference",
            ]
        )
        for snapshot in display_qs:
            writer.writerow(
                [
                    snapshot.business_date.isoformat(),
                    snapshot.location_name,
                    snapshot.get_source_display(),
                    snapshot.get_sync_mode_display(),
                    f"{snapshot.net_sales:.2f}",
                    f"{snapshot.gross_sales:.2f}",
                    f"{snapshot.refunds:.2f}",
                    snapshot.transactions,
                    snapshot.covers,
                    f"{snapshot.cash_sales:.2f}",
                    f"{snapshot.card_sales:.2f}",
                    f"{snapshot.digital_sales:.2f}",
                    f"{snapshot.beer_sales:.2f}",
                    f"{snapshot.spirits_sales:.2f}",
                    f"{snapshot.wine_sales:.2f}",
                    f"{snapshot.soft_sales:.2f}",
                    f"{snapshot.food_sales:.2f}",
                    f"{snapshot.other_sales:.2f}",
                    snapshot.external_reference,
                ]
            )
        return response

    context = {
        "hero_signals": hero_signals,
        "metric_cards": metric_cards,
        "attention_items": attention_items,
        "margin_mix": margin_mix,
        "ops_handoff": ops_handoff,
        "connector_rows": connector_rows[:4],
        "snapshots": snapshots,
        "snapshot_count": display_qs.count(),
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "filter_query": build_query_string(request, exclude_keys={"export"}),
        "filters_active": filters_active,
        "filter_presets": filter_presets,
        "active_filter_count": sum([bool(query), bool(selected_source), selected_range != "30"]),
        "query": query,
        "selected_source": selected_source,
        "selected_range": selected_range,
        "selected_source_label": dict(SalesSnapshot.Source.choices).get(selected_source, ""),
        "selected_range_label": f"Last {selected_range} Days",
        "selected_preset_label": next(
            (
                preset["label"]
                for preset in filter_presets
                if preset["active"] and preset["query"]
            ),
            "",
        ),
        "source_choices": SalesSnapshot.Source.choices,
        "sync_summary": sync_summary,
    }
    return render(request, "sales/list.html", context)


@management_required
def sync_center(request):
    integrations = list(_integration_queryset())
    connector_rows = _build_sync_center_rows(request, integrations)
    mappings = PosLocationMapping.objects.select_related("integration").order_by(
        "integration__label",
        "-is_primary",
        "internal_location_name",
    )
    recent_runs = PosSyncRun.objects.select_related("integration", "triggered_by")[:8]
    recent_events = PosWebhookEvent.objects.select_related("integration")[:8]
    sync_summary = _build_sync_summary(integrations)
    for run in recent_runs:
        run.status_tone = (
            "ok"
            if run.status == PosSyncRun.Status.SUCCESS
            else "warn"
            if run.status in {PosSyncRun.Status.RUNNING, PosSyncRun.Status.PARTIAL}
            else "alert"
        )
    for event in recent_events:
        event.status_tone = (
            "ok"
            if event.status == PosWebhookEvent.Status.PROCESSED
            else "warn"
            if event.status == PosWebhookEvent.Status.RECEIVED
            else "alert"
        )

    attention_items = []
    if not integrations:
        attention_items.append(
            {
                "label": "First live feed",
                "value": "Not configured",
                "copy": "Create the first POS connector before turning on scheduled imports or webhooks.",
                "tone": "alert",
                "action_label": "Add connector",
                "url_name": "sales:integration_add",
            }
        )
    elif sync_summary["connectors_needing_attention"]:
        attention_items.append(
            {
                "label": "Feed health",
                "value": f"{sync_summary['connectors_needing_attention']} need review",
                "copy": "One or more connectors are due, errored, or still missing mapping.",
                "tone": "warn",
                "action_label": "Add mapping",
                "url_name": "sales:mapping_add",
            }
        )
    if sync_summary["webhook_queue_count"]:
        attention_items.append(
            {
                "label": "Webhook backlog",
                "value": sync_summary["webhook_queue_count"],
                "copy": "Inbound webhook events are waiting to be processed.",
                "tone": "warn",
                "action_label": "Review queue",
                "url_name": "sales:sync_center",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "POS control",
                "value": "Healthy",
                "copy": "Connectors, mappings, and webhook intake are currently under control.",
                "tone": "ok",
                "action_label": "Open sales",
                "url_name": "sales:list",
            }
        )

    context = {
        "attention_items": attention_items,
        "connector_rows": connector_rows,
        "mappings": mappings[:10],
        "recent_runs": recent_runs,
        "recent_events": recent_events,
        "sync_summary": sync_summary,
    }
    return render(request, "sales/sync_center.html", context)


@management_required
def add_sales_snapshot(request):
    if request.method == "POST":
        form = SalesSnapshotForm(request.POST)
        if form.is_valid():
            snapshot = form.save(commit=False)
            snapshot.uploaded_by = request.user
            snapshot.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=snapshot,
                summary=f"Logged sales snapshot for {snapshot.business_date:%d %b}",
                details={
                    "source": snapshot.source,
                    "sync_mode": snapshot.sync_mode,
                    "net_sales": f"{snapshot.net_sales:.2f}",
                    "location_name": snapshot.location_name,
                },
            )
            messages.success(request, "Sales snapshot logged.")
            return redirect("sales:list")
    else:
        form = SalesSnapshotForm()

    return render(
        request,
        "sales/form.html",
        {
            "form": form,
            "page_title": "Log Sales Snapshot",
            "submit_label": "Save Snapshot",
        },
    )


@management_required
def edit_sales_snapshot(request, pk):
    snapshot = get_object_or_404(SalesSnapshot, pk=pk)

    if request.method == "POST":
        form = SalesSnapshotForm(request.POST, instance=snapshot)
        if form.is_valid():
            snapshot = form.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.UPDATE,
                target=snapshot,
                summary=f"Updated sales snapshot for {snapshot.business_date:%d %b}",
                details={
                    "source": snapshot.source,
                    "sync_mode": snapshot.sync_mode,
                    "net_sales": f"{snapshot.net_sales:.2f}",
                    "location_name": snapshot.location_name,
                },
            )
            messages.success(request, "Sales snapshot updated.")
            return redirect("sales:list")
    else:
        form = SalesSnapshotForm(instance=snapshot)

    return render(
        request,
        "sales/form.html",
        {
            "form": form,
            "page_title": "Edit Sales Snapshot",
            "submit_label": "Save Changes",
            "snapshot": snapshot,
        },
    )


@management_required
def add_pos_integration(request):
    if request.method == "POST":
        form = PosIntegrationForm(request.POST)
        if form.is_valid():
            integration = form.save(commit=False)
            if not integration.webhook_secret:
                integration.webhook_secret = secrets.token_hex(16)
            integration.created_by = request.user
            integration.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=integration,
                summary=f"Created POS connector {integration.label}",
                details={
                    "provider": integration.provider,
                    "sync_interval_minutes": integration.sync_interval_minutes,
                },
            )
            messages.success(request, "POS connector created.")
            return redirect("sales:sync_center")
    else:
        form = PosIntegrationForm()

    return render(
        request,
        "sales/integration_form.html",
        {
            "form": form,
            "page_title": "Add POS Connector",
            "submit_label": "Save Connector",
        },
    )


@management_required
def edit_pos_integration(request, pk):
    integration = get_object_or_404(PosIntegration, pk=pk)

    if request.method == "POST":
        form = PosIntegrationForm(request.POST, instance=integration)
        if form.is_valid():
            integration = form.save(commit=False)
            if not integration.webhook_secret:
                integration.webhook_secret = secrets.token_hex(16)
            integration.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.UPDATE,
                target=integration,
                summary=f"Updated POS connector {integration.label}",
                details={
                    "provider": integration.provider,
                    "sync_interval_minutes": integration.sync_interval_minutes,
                },
            )
            messages.success(request, "POS connector updated.")
            return redirect("sales:sync_center")
    else:
        form = PosIntegrationForm(instance=integration)

    return render(
        request,
        "sales/integration_form.html",
        {
            "form": form,
            "page_title": "Edit POS Connector",
            "submit_label": "Save Changes",
            "integration": integration,
        },
    )


@management_required
def add_pos_location_mapping(request):
    if request.method == "POST":
        form = PosLocationMappingForm(request.POST)
        if form.is_valid():
            mapping = form.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=mapping,
                summary=f"Created location mapping for {mapping.integration.label}",
                details={
                    "external_location_id": mapping.external_location_id,
                    "internal_location_name": mapping.internal_location_name,
                },
            )
            messages.success(request, "Location mapping created.")
            return redirect("sales:sync_center")
    else:
        form = PosLocationMappingForm()

    return render(
        request,
        "sales/mapping_form.html",
        {
            "form": form,
            "page_title": "Add Location Mapping",
            "submit_label": "Save Mapping",
        },
    )


@management_required
@require_POST
def run_integration_sync(request, pk):
    integration = get_object_or_404(PosIntegration, pk=pk)
    try:
        run = sync_integration(
            integration,
            business_date=timezone.localdate(),
            trigger_type=PosSyncRun.TriggerType.MANUAL,
            triggered_by=request.user,
        )
        record_audit_event(
            request,
            action=AuditEvent.Action.UPDATE,
            target=integration,
            summary=f"Ran manual sync for {integration.label}",
            details={
                "snapshots_imported": run.snapshots_imported,
                "imported_net_sales": f"{run.imported_net_sales:.2f}",
            },
        )
        messages.success(
            request,
            f"{integration.label} synced successfully with {run.snapshots_imported} snapshot(s).",
        )
    except Exception as exc:
        messages.error(request, f"{integration.label} sync failed: {exc}")
    return redirect("sales:sync_center")


@management_required
@require_POST
def run_due_syncs(request):
    integrations = list(_integration_queryset().filter(is_enabled=True))
    sync_targets = [
        integration
        for integration in integrations
        if _integration_health_state(integration) in {"warn", "alert"}
    ]
    if not sync_targets:
        messages.info(request, "No connectors currently need a due sync run.")
        return redirect("sales:sync_center")

    completed = 0
    failed_labels = []
    for integration in sync_targets:
        try:
            sync_integration(
                integration,
                business_date=timezone.localdate(),
                trigger_type=PosSyncRun.TriggerType.SCHEDULED,
                triggered_by=request.user,
            )
            completed += 1
        except Exception:
            failed_labels.append(integration.label)

    record_audit_event(
        request,
        action=AuditEvent.Action.UPDATE,
        summary=f"Triggered {completed} scheduled sync run(s)",
        details={"failed_connectors": failed_labels},
    )
    if completed:
        messages.success(request, f"Triggered {completed} due connector sync run(s).")
    if failed_labels:
        messages.warning(
            request,
            f"Some connectors still failed: {', '.join(failed_labels)}.",
        )
    return redirect("sales:sync_center")


@csrf_exempt
@require_POST
def receive_pos_webhook(request, pk):
    integration = get_object_or_404(
        PosIntegration.objects.filter(is_enabled=True, webhook_enabled=True),
        pk=pk,
    )
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)

    event = PosWebhookEvent.objects.create(
        integration=integration,
        event_type=str(payload.get("event_type", "sales.sync")),
        external_event_id=str(payload.get("event_id", ""))[:120],
        payload=payload,
    )

    provided_secret = request.headers.get("X-BarrelBoss-Webhook-Secret", "")
    if integration.webhook_secret and provided_secret != integration.webhook_secret:
        event.status = PosWebhookEvent.Status.REJECTED
        event.processed_at = timezone.now()
        event.notes = "Webhook secret did not match."
        event.save(update_fields=["status", "processed_at", "notes"])
        return JsonResponse({"detail": "Invalid webhook secret."}, status=403)

    try:
        business_date = parse_business_date(payload.get("business_date"))
    except ValueError:
        event.status = PosWebhookEvent.Status.FAILED
        event.processed_at = timezone.now()
        event.notes = "Invalid business_date provided."
        event.save(update_fields=["status", "processed_at", "notes"])
        return JsonResponse({"detail": "Invalid business_date."}, status=400)

    try:
        run = sync_integration(
            integration,
            business_date=business_date,
            trigger_type=PosSyncRun.TriggerType.WEBHOOK,
            selected_external_location_id=str(payload.get("external_location_id", "")),
        )
    except Exception as exc:
        event.status = PosWebhookEvent.Status.FAILED
        event.processed_at = timezone.now()
        event.notes = str(exc)
        event.save(update_fields=["status", "processed_at", "notes"])
        return JsonResponse({"detail": str(exc)}, status=500)

    event.status = PosWebhookEvent.Status.PROCESSED
    event.processed_at = timezone.now()
    event.notes = f"Imported {run.snapshots_imported} snapshot(s)."
    event.save(update_fields=["status", "processed_at", "notes"])
    return JsonResponse(
        {
            "detail": "Webhook processed.",
            "snapshots_imported": run.snapshots_imported,
            "integration": integration.label,
        },
        status=202,
    )
