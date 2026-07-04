import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from apps.shifts.models import Shift
from apps.stock.models import StockItem
from taptrack.pagination import build_query_string, paginate_collection

from .forms import SalesSnapshotForm
from .models import SalesSnapshot


def _sum_shift_hours_for_range(start_date, end_date):
    shifts = Shift.objects.filter(shift_date__range=(start_date, end_date))
    return round(sum(shift.duration_hours for shift in shifts), 1)


def _rate(part, whole):
    if not whole:
        return 0
    return round((part / whole) * 100, 1)


def _currency(value):
    return f"£{value:,.2f}"


def _build_attention_items(*, latest_snapshot, today_snapshot, refund_rate, stock_risks):
    attention_items = []

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
                "copy": "Revenue, payment reconciliation, and stock-linked service pressure are currently under control.",
                "tone": "ok",
                "action_label": "Review sales",
                "url_name": "sales:list",
            }
        )

    return attention_items


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
    today_sales_per_labor_hour = (
        round(today_snapshot.net_sales / Decimal(str(today_labor_hours)), 2)
        if today_snapshot and today_labor_hours
        else Decimal("0.00")
    )

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
            category__in=[
                StockItem.Category.SOFT_DRINKS,
                StockItem.Category.MIXERS,
            ],
            quantity__lte=F("minimum_level"),
        ).count(),
    }
    total_stock_risk_lines = sum(stock_risks.values())

    attention_items = _build_attention_items(
        latest_snapshot=latest_snapshot,
        today_snapshot=today_snapshot,
        refund_rate=refund_rate,
        stock_risks=stock_risks,
    )

    hero_signals = [
        {
            "label": "Sync status",
            "value": (
                "Live today"
                if today_snapshot
                else (
                    f"Last sync {latest_snapshot.business_date:%d %b}"
                    if latest_snapshot
                    else "No snapshots"
                )
            ),
            "copy": (
                f"{latest_snapshot.get_source_display()} via {latest_snapshot.get_sync_mode_display()}."
                if latest_snapshot
                else "Connect a POS feed or log the first daily snapshot."
            ),
            "tone": "ok" if today_snapshot else "warn",
        },
        {
            "label": "Net sales today",
            "value": _currency(today_snapshot.net_sales) if today_snapshot else "£0.00",
            "copy": (
                f"{today_snapshot.transactions} transactions across {today_snapshot.covers} covers."
                if today_snapshot
                else "No sales have been recorded for today yet."
            ),
            "tone": "neutral",
        },
        {
            "label": "Tips today",
            "value": _currency(today_snapshot.tips) if today_snapshot else "£0.00",
            "copy": (
                f"{_currency(today_snapshot.spend_per_cover)} spend per cover."
                if today_snapshot and today_snapshot.covers
                else "Spend-per-cover updates once covers are logged."
            ),
            "tone": "ok",
        },
        {
            "label": "Sales / labor hour",
            "value": _currency(today_sales_per_labor_hour) if today_snapshot else "£0.00",
            "copy": (
                f"{today_labor_hours} scheduled labor hour(s) linked to today’s trading."
                if today_labor_hours
                else "No shift hours are scheduled for today yet."
            ),
            "tone": "neutral",
        },
    ]

    metric_cards = [
        {
            "label": "Net Sales In View",
            "value": _currency(total_net_sales),
            "state": f"{allowed_ranges[selected_range]} day window",
            "state_tone": "ok",
            "summary": f"{display_qs.count()} synced day(s) are included in the current view.",
            "note": "Use this as the current revenue pulse for the selected POS source and date range.",
            "actions": [
                {"label": "Log snapshot", "url_name": "sales:add"},
                {"label": "Export CSV", "href": f"?{build_query_string(request, exclude_keys={'export'})}&export=csv" if build_query_string(request, exclude_keys={'export'}) else "?export=csv"},
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
                {"label": "Review sales", "url_name": "sales:list"},
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
            "note": "This ties the sales layer directly back into rota planning.",
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
                {"label": "Review snapshots", "url_name": "sales:list"},
            ],
            "tone": "warn",
        },
        {
            "label": "Tips Captured",
            "value": _currency(totals["tips"] or Decimal("0.00")),
            "state": (
                f"{_rate(totals['tips'] or Decimal('0.00'), total_net_sales):.1f}% of net sales"
                if total_net_sales
                else "No sales yet"
            ),
            "state_tone": "neutral",
            "summary": "Tip visibility is the starting point for premium labor and payroll workflows.",
            "note": "This lays the groundwork for tip pooling and payroll export next.",
            "actions": [
                {"label": "Open sales", "url_name": "sales:list"},
            ],
            "tone": "neutral",
        },
        {
            "label": "At-Risk Service Lines",
            "value": total_stock_risk_lines,
            "state": "Restock pressure" if total_stock_risk_lines else "Stable board",
            "state_tone": "alert" if total_stock_risk_lines else "ok",
            "summary": (
                f"{stock_risks['beer']} beer, {stock_risks['spirits']} spirits, {stock_risks['wine']} wine, and {stock_risks['soft']} soft-drink lines are low."
                if total_stock_risk_lines
                else "Sales-linked categories are currently above their minimum thresholds."
            ),
            "note": "This is the hand-off point between POS trading data and cellar/inventory action.",
            "actions": [
                {"label": "Open stock", "url_name": "stock:list"},
            ],
            "tone": "alert",
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
    category_mix = []
    for label, value, risk_lines in category_fields:
        share = _rate(value, total_net_sales)
        category_mix.append(
            {
                "label": label,
                "value": _currency(value),
                "share": f"{share:.1f}%",
                "meta": (
                    f"{risk_lines} low stock line(s)"
                    if risk_lines
                    else "No direct stock pressure flagged"
                ),
            }
        )

    payment_breakdown = [
        {
            "label": "Card",
            "value": _currency(total_card_sales),
            "share": f"{_rate(total_card_sales, total_net_sales):.1f}%",
            "meta": "Primary modern tender mix",
        },
        {
            "label": "Cash",
            "value": _currency(total_cash_sales),
            "share": f"{_rate(total_cash_sales, total_net_sales):.1f}%",
            "meta": "Watch this against till-close cashing-up",
        },
        {
            "label": "Digital / Other",
            "value": _currency(total_digital_sales),
            "share": f"{_rate(total_digital_sales, total_net_sales):.1f}%",
            "meta": "Apps, house accounts, and alternative tenders",
        },
    ]

    latest_snapshot_summary = []
    if latest_snapshot:
        latest_snapshot_summary = [
            {
                "label": "Latest source",
                "value": latest_snapshot.get_source_display(),
                "meta": latest_snapshot.get_sync_mode_display(),
            },
            {
                "label": "Business date",
                "value": latest_snapshot.business_date.strftime("%a %d %b"),
                "meta": latest_snapshot.location_name,
            },
            {
                "label": "Payment gap",
                "value": _currency(abs(latest_snapshot.payment_gap)),
                "meta": "Reconcile against tenders",
            },
            {
                "label": "Category gap",
                "value": _currency(abs(latest_snapshot.category_gap)),
                "meta": "Unmapped sales mix remaining",
            },
        ]

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
        {
            "label": "Manual Close",
            "query": f"range={selected_range}&source={SalesSnapshot.Source.MANUAL}",
            "active": selected_source == SalesSnapshot.Source.MANUAL and not query,
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
        "category_mix": category_mix,
        "payment_breakdown": payment_breakdown,
        "latest_snapshot": latest_snapshot,
        "latest_snapshot_summary": latest_snapshot_summary,
        "snapshots": snapshots,
        "snapshot_count": display_qs.count(),
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "filter_query": build_query_string(request, exclude_keys={"export"}),
        "filters_active": filters_active,
        "filter_presets": filter_presets,
        "active_filter_count": sum(
            [bool(query), bool(selected_source), selected_range != "30"]
        ),
        "query": query,
        "selected_source": selected_source,
        "selected_range": selected_range,
        "selected_source_label": dict(SalesSnapshot.Source.choices).get(
            selected_source, ""
        ),
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
    }
    return render(request, "sales/list.html", context)


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

