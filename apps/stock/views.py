import csv
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.push import send_stock_count_push_notification
from apps.accounts.scoping import current_venue_or_404
from apps.accounts.permissions import active_venue_required, is_management, management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from taptrack.pagination import build_query_string, paginate_collection
from taptrack.module_ui import build_module_link, build_module_panel, build_module_snapshot

from .forms import StockItemForm
from .models import StockItem


STOCK_FOCUS_GROUPS = {
    "cellar": {
        "label": "Cellar",
        "categories": (
            StockItem.Category.BEER_BARRELS,
            StockItem.Category.SOFT_DRINKS,
            StockItem.Category.MIXERS,
        ),
        "copy": "Beer, packaged softs, and mixers that can stop service fastest.",
    },
    "backbar": {
        "label": "Back Bar",
        "categories": (
            StockItem.Category.SPIRITS,
            StockItem.Category.WINE,
            StockItem.Category.GARNISHES,
        ),
        "copy": "Spirits, wine, and bar garnish lines that shape the back-bar offer.",
    },
    "service": {
        "label": "Service Kit",
        "categories": (
            StockItem.Category.GLASSWARE,
            StockItem.Category.CLEANING,
            StockItem.Category.SNACKS,
        ),
        "copy": "Glassware, cleaning, and service support lines needed to keep the floor moving.",
    },
}


def _stock_workspace_url(*, section="stock-section-board", **params):
    filtered_params = {key: value for key, value in params.items() if value not in {"", None}}
    url = reverse("stock:list")
    if filtered_params:
        url = f"{url}?{urlencode(filtered_params)}"
    if section:
        url = f"{url}#{section}"
    return url


def _stock_focus_url(value):
    return f"{reverse('stock:list')}?focus={value}" if value else reverse("stock:list")


def _supplier_contact_summary(supplier):
    if not supplier:
        return "Supplier not linked"

    parts = []
    if supplier.contact_name:
        parts.append(supplier.contact_name)
    if supplier.phone:
        parts.append(supplier.phone)
    elif supplier.email:
        parts.append(supplier.email)

    return " · ".join(parts) if parts else "Contact details missing"


def _count_status_payload(item, *, now):
    if not item.last_counted_at:
        return {
            "count_status_key": "missing",
            "count_status_label": "Never counted",
            "count_status_badge_class": "badge-stock-critical",
            "count_status_note": "No stock count has been recorded for this line yet.",
            "last_counted_label": "Never counted",
        }

    local_count = timezone.localtime(item.last_counted_at)
    age_days = max((now.date() - local_count.date()).days, 0)
    if age_days >= 7:
        status_key = "stale"
        status_label = "Count overdue"
        badge_class = "badge-stock-low"
        status_note = f"Last counted {age_days} day(s) ago."
    elif age_days >= 3:
        status_key = "watch"
        status_label = "Count due soon"
        badge_class = "badge-stock-watch"
        status_note = f"Last counted {age_days} day(s) ago."
    else:
        status_key = "fresh"
        status_label = "Recently counted"
        badge_class = "badge-stock-healthy"
        status_note = f"Counted {age_days} day(s) ago."

    return {
        "count_status_key": status_key,
        "count_status_label": status_label,
        "count_status_badge_class": badge_class,
        "count_status_note": status_note,
        "last_counted_label": local_count.strftime("%d %b %Y %H:%M"),
    }


def _safe_next_url(request, fallback):
    redirect_to = request.POST.get("next") or request.GET.get("next")
    if redirect_to and url_has_allowed_host_and_scheme(
        redirect_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect_to
    return fallback


def _staff_count_return_url(*, query="", category="", urgency="all"):
    return _stock_workspace_url(
        focus="uncounted",
        q=query or None,
        category=category or None,
        urgency=urgency if urgency != "all" else None,
    )


@active_venue_required
def list_items(request):
    selected_focus = request.GET.get("focus", "")
    selected_category = request.GET.get("category", "")
    selected_urgency = request.GET.get("urgency", "all")
    query = (request.GET.get("q") or "").strip()
    management_view = is_management(request.user, request=request)
    venue = current_venue_or_404(request)
    now = timezone.now()
    today = timezone.localdate()
    stale_count_cutoff = now - timedelta(days=7)

    focus_choices = [
        ("", "All Zones"),
        *[
            (key, config["label"])
            for key, config in STOCK_FOCUS_GROUPS.items()
        ],
        ("uncounted", "Needs Count"),
        ("unlinked", "Needs Supplier"),
    ]
    allowed_focus_values = {value for value, _label in focus_choices}
    if selected_focus not in allowed_focus_values:
        selected_focus = ""

    urgency_choices = [
        ("all", "All Urgency Bands"),
        ("critical", "Critical"),
        ("low", "Low"),
        ("watch", "Watch"),
        ("healthy", "Healthy"),
    ]
    allowed_urgency_values = {value for value, _label in urgency_choices}
    if selected_urgency not in allowed_urgency_values:
        selected_urgency = "all"

    items_qs = StockItem.objects.select_related("supplier").filter(
        is_active=True,
        venue=venue,
    )

    if selected_focus in STOCK_FOCUS_GROUPS:
        items_qs = items_qs.filter(
            category__in=STOCK_FOCUS_GROUPS[selected_focus]["categories"]
        )
    elif selected_focus == "uncounted":
        items_qs = items_qs.filter(
            Q(last_counted_at__isnull=True) | Q(last_counted_at__lt=stale_count_cutoff)
        )
    elif selected_focus == "unlinked":
        items_qs = items_qs.filter(supplier__isnull=True)

    if selected_category and selected_category in StockItem.Category.values:
        items_qs = items_qs.filter(category=selected_category)

    if query:
        items_qs = items_qs.filter(
            Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(unit__icontains=query)
            | Q(notes__icontains=query)
            | Q(supplier__name__icontains=query)
        )

    inventory_items = list(items_qs)
    urgency_labels = {
        "critical": "Critical",
        "low": "Low",
        "watch": "Watch",
        "healthy": "Healthy",
    }
    urgency_badge_classes = {
        "critical": "badge-stock-critical",
        "low": "badge-stock-low",
        "watch": "badge-stock-watch",
        "healthy": "badge-stock-healthy",
    }
    count_status_counts = {
        "missing": 0,
        "stale": 0,
        "watch": 0,
        "fresh": 0,
    }
    urgency_counts = {key: 0 for key in urgency_labels}
    total_units = 0
    stock_value_estimate = 0
    restock_gap_units = 0
    recently_restocked_count = 0

    for item in inventory_items:
        minimum_level = max(item.minimum_level or 0, 0)
        stock_gap = max(minimum_level - item.quantity, 0)
        total_units += item.quantity
        stock_value_estimate += item.quantity * item.cost

        if item.quantity <= 0:
            stock_band = "critical"
            stock_note = "Out of stock"
        elif minimum_level > 0 and item.quantity <= minimum_level:
            if item.quantity <= max(1, int(round(minimum_level * 0.5))):
                stock_band = "critical"
                stock_note = f"{stock_gap} below minimum"
            else:
                stock_band = "low"
                stock_note = f"{stock_gap} below minimum" if stock_gap else "At minimum threshold"
        elif minimum_level > 0 and item.quantity <= int(round(minimum_level * 1.5)):
            stock_band = "watch"
            stock_note = "Buffer running low"
        else:
            stock_band = "healthy"
            stock_note = "Healthy stock buffer"

        item.stock_band = stock_band
        item.stock_band_label = urgency_labels[stock_band]
        item.stock_band_badge_class = urgency_badge_classes[stock_band]
        item.stock_note = stock_note
        item.stock_gap = stock_gap
        item.minimum_display = minimum_level
        item.value_estimate = item.quantity * item.cost
        item.last_restocked_label = (
            item.last_restocked.strftime("%d %b %Y")
            if item.last_restocked
            else "Not recorded"
        )
        count_payload = _count_status_payload(item, now=now)
        for key, value in count_payload.items():
            setattr(item, key, value)
        item.supplier_contact_summary = _supplier_contact_summary(item.supplier)
        urgency_counts[stock_band] += 1
        count_status_counts[item.count_status_key] += 1
        if stock_band in {"critical", "low"}:
            restock_gap_units += stock_gap
        if item.last_restocked and (today - item.last_restocked).days <= 7:
            recently_restocked_count += 1

    urgency_priority = {"critical": 0, "low": 1, "watch": 2, "healthy": 3}
    inventory_items.sort(key=lambda item: (urgency_priority[item.stock_band], item.name.lower()))

    if selected_urgency == "all":
        items = inventory_items
    else:
        items = [item for item in inventory_items if item.stock_band == selected_urgency]

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="barrelboss-stock.csv"'
        writer = csv.writer(response)
        writer.writerow(["BarrelBoss Stock Export"])
        writer.writerow(
            [
                "Item",
                "Category",
                "Quantity",
                "Unit",
                "Minimum",
                "Stock Gap",
                "Urgency",
                "Count Status",
                "Supplier",
                "Cost",
                "Estimated Value",
            ]
        )
        for item in items:
            writer.writerow(
                [
                    item.name,
                    item.get_category_display(),
                    item.quantity,
                    item.get_unit_display(),
                    item.minimum_display,
                    item.stock_gap,
                    item.stock_band_label,
                    item.count_status_label,
                    item.supplier.name if item.supplier else "-",
                    f"{item.cost:.2f}",
                    f"{item.value_estimate:.2f}",
                ]
            )
        return response

    page_obj = paginate_collection(request, items, per_page=12)
    filter_query = build_query_string(request, exclude_keys={"export"})
    category_labels = dict(StockItem.Category.choices)
    focus_labels = dict(focus_choices)
    urgency_label_map = dict(urgency_choices)
    filters_active = bool(query or selected_focus or selected_category or selected_urgency != "all")
    filter_presets = [
        {"label": "All Stock", "query": "", "active": not filters_active},
        {"label": "Cellar", "query": "focus=cellar", "active": selected_focus == "cellar" and not query and not selected_category and selected_urgency == "all"},
        {"label": "Back Bar", "query": "focus=backbar", "active": selected_focus == "backbar" and not query and not selected_category and selected_urgency == "all"},
        {"label": "Service Kit", "query": "focus=service", "active": selected_focus == "service" and not query and not selected_category and selected_urgency == "all"},
        {"label": "Critical Risk", "query": "urgency=critical", "active": selected_urgency == "critical" and not query and not selected_category and not selected_focus},
        {"label": "Needs Count", "query": "focus=uncounted", "active": selected_focus == "uncounted" and not query and not selected_category and selected_urgency == "all"},
    ]
    attention_items = []
    if urgency_counts["critical"]:
        attention_items.append(
            {
                "label": "Critical risk",
                "value": f"{urgency_counts['critical']} line(s)",
                "copy": "These items are out of stock or severely below minimum and should be cleared first.",
                "tone": "alert",
                "action_label": "Open critical",
                "url_name": "stock:list",
                "query": "urgency=critical",
                "href": _stock_workspace_url(urgency="critical"),
            }
        )
    if restock_gap_units:
        attention_items.append(
            {
                "label": "Restock gap",
                "value": f"{restock_gap_units} units",
                "copy": "This is the quantity needed to bring low and critical lines back to minimum.",
                "tone": "warn",
                "action_label": "Open low stock",
                "url_name": "stock:list",
                "query": "urgency=low",
                "href": _stock_workspace_url(urgency="low"),
            }
        )
    if urgency_counts["watch"]:
        attention_items.append(
            {
                "label": "Watch list",
                "value": f"{urgency_counts['watch']} line(s)",
                "copy": "These buffers are thinning and can become tomorrow’s urgent queue if left untouched.",
                "tone": "neutral",
                "action_label": "Open watch list",
                "url_name": "stock:list",
                "query": "urgency=watch",
                "href": _stock_workspace_url(urgency="watch"),
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Inventory attention",
                "value": "Stable board",
                "copy": "No critical or low-stock issues are showing in the current inventory view.",
                "tone": "ok",
                "action_label": "Review healthy",
                "url_name": "stock:list",
                "query": "urgency=healthy",
                "href": _stock_workspace_url(urgency="healthy"),
            }
        )

    if urgency_counts["critical"]:
        primary_title = "Review critical stock"
        primary_copy = (
            f"{urgency_counts['critical']} line(s) are already out or well below minimum and need attention first."
        )
        primary_url = _stock_workspace_url(urgency="critical")
        primary_label = "Open critical stock"
    elif urgency_counts["low"]:
        primary_title = "Work the low-stock queue"
        primary_copy = (
            f"{urgency_counts['low']} line(s) are below safe working level and should be queued for replenishment."
        )
        primary_url = _stock_workspace_url(urgency="low")
        primary_label = "Open low stock"
    elif count_status_counts["missing"] or count_status_counts["stale"]:
        primary_title = "Tighten stock count discipline"
        primary_copy = (
            f"{count_status_counts['missing'] + count_status_counts['stale']} line(s) need a fresh count before the board can be trusted cleanly."
        )
        primary_url = _stock_workspace_url(focus="uncounted")
        primary_label = "Open count queue"
    elif management_view:
        primary_title = "Add or tidy inventory"
        primary_copy = (
            "The urgent queue is clear, so this is the right time to clean the catalogue or add new stock lines."
        )
        primary_url = reverse("stock:add")
        primary_label = "Add stock item"
    else:
        primary_title = "Review the watch list"
        primary_copy = (
            "No urgent shortage is showing, so use the watch list to stop tomorrow's problems early."
        )
        primary_url = _stock_workspace_url(urgency="watch")
        primary_label = "Open watch list"

    display_item_count = len(items)
    module_panel = build_module_panel(
        hero_class="inventory-hero",
        kicker="Inventory",
        badge="Stock Control",
        title="Keep stock visible and current.",
        copy="Work shortages, counts, and supplier follow-up from one board.",
        primary_title=primary_title,
        primary_copy=primary_copy,
        primary_url=primary_url,
        primary_label=primary_label,
        utility_links=[
            *(
                [build_module_link("Create order", reverse("orders:add"))]
                if management_view
                else []
            ),
            *(
                [build_module_link("Open suppliers", reverse("suppliers:list"))]
                if management_view
                else []
            ),
            build_module_link(
                "Export CSV",
                f"{reverse('stock:list')}?{filter_query}&export=csv"
                if filter_query
                else f"{reverse('stock:list')}?export=csv",
            ),
        ],
        toolbar_notes=[
            f"{display_item_count} shown",
            f"{total_units} units",
            f"{count_status_counts['missing'] + count_status_counts['stale']} count due",
        ],
    )
    module_snapshots = [
        build_module_snapshot(
            label="Immediate action",
            state=(
                f"{urgency_counts['critical']} critical"
                if urgency_counts["critical"]
                else ("Restock now" if urgency_counts["low"] else "Clear")
            ),
            tone="alert" if urgency_counts["critical"] else ("warn" if urgency_counts["low"] else "ok"),
            value=urgency_counts["critical"] + urgency_counts["low"],
            copy=(
                "Critical and low-stock lines combined into one queue that should be reviewed before ordinary restocking."
            ),
            action_label="Open critical" if urgency_counts["critical"] else "Open low stock",
            action_url=(
                _stock_workspace_url(urgency="critical")
                if urgency_counts["critical"]
                else _stock_workspace_url(urgency="low")
            ),
        ),
        build_module_snapshot(
            label="Restock gap",
            state="Replenish" if restock_gap_units else "Covered",
            tone="warn" if restock_gap_units else "ok",
            value=restock_gap_units,
            copy=(
                "Units still needed to bring low and critical lines back to their minimum working level."
            ),
            action_label="Create order" if management_view else "Review low stock",
            action_url=(
                reverse("orders:add")
                if management_view
                else _stock_workspace_url(urgency="low")
            ),
        ),
        build_module_snapshot(
            label="Count discipline",
            state=(
                f"{count_status_counts['missing']} missing"
                if count_status_counts["missing"]
                else ("Overdue" if count_status_counts["stale"] else "In cycle")
            ),
            tone="alert" if count_status_counts["missing"] else ("warn" if count_status_counts["stale"] else "ok"),
            value=count_status_counts["missing"] + count_status_counts["stale"],
            copy=(
                "Lines with no recent count record, which is often where cellar decisions become guesswork."
            ),
            action_label="Open count queue",
            action_url=_stock_workspace_url(focus="uncounted"),
        ),
    ]

    scoped_items = items

    focus_zone_cards = []
    for focus_key, config in STOCK_FOCUS_GROUPS.items():
        zone_items = [
            item
            for item in scoped_items
            if item.category in config["categories"]
        ]
        urgent_count = sum(
            1 for item in zone_items if item.stock_band in {"critical", "low"}
        )
        critical_count = sum(1 for item in zone_items if item.stock_band == "critical")
        zone_gap_units = sum(item.stock_gap for item in zone_items)
        focus_zone_cards.append(
            {
                "label": config["label"],
                "copy": config["copy"],
                "value": f"{urgent_count} urgent",
                "note": (
                    f"{critical_count} critical · {zone_gap_units} unit gap"
                    if zone_items
                    else "No lines in scope"
                ),
                "tone": "alert" if critical_count else ("warn" if urgent_count else "ok"),
                "url": _stock_workspace_url(focus=focus_key),
            }
        )

    supplier_actions = defaultdict(
        lambda: {"title": "", "meta": "", "note": "", "gap": 0, "lines": 0, "critical": 0}
    )
    unlinked_urgent_items = []
    for item in scoped_items:
        if item.stock_band not in {"critical", "low"}:
            continue

        if item.supplier:
            entry = supplier_actions[item.supplier_id]
            entry["title"] = item.supplier.name
            entry["meta"] = item.supplier_contact_summary
            entry["gap"] += item.stock_gap
            entry["lines"] += 1
            entry["critical"] += 1 if item.stock_band == "critical" else 0
            entry["note"] = item.name if not entry["note"] else entry["note"]
        else:
            unlinked_urgent_items.append(item)

    supplier_action_rows = [
        {
            "title": entry["title"],
            "meta": entry["meta"],
            "note": f"{entry['lines']} line(s) short · {entry['gap']} unit gap",
            "badge": "Call now" if entry["critical"] else "Queue order",
            "tone": "alert" if entry["critical"] else "warn",
            "href": (
                f"{reverse('suppliers:list')}?{urlencode({'q': entry['title']})}"
                if management_view
                else reverse("orders:add")
            ),
        }
        for entry in sorted(
            supplier_actions.values(),
            key=lambda row: (-row["critical"], -row["gap"], row["title"].lower()),
        )[:4]
    ]
    if unlinked_urgent_items:
        supplier_action_rows.append(
            {
                "title": "Unlinked urgent stock",
                "meta": "Catalogue cleanup needed",
                "note": ", ".join(item.name for item in unlinked_urgent_items[:3]),
                "badge": "Assign supplier",
                "tone": "alert",
                "href": (
                    _stock_workspace_url(focus="unlinked")
                    if management_view
                    else reverse("orders:add")
                ),
            }
        )

    count_priority = {"missing": 0, "stale": 1, "watch": 2}
    count_discipline_rows = [
        {
            "title": item.name,
            "meta": f"{item.get_category_display()} · {item.count_status_label}",
            "note": (
                f"{item.count_status_note} · Restocked {item.last_restocked_label}."
                if item.last_restocked
                else item.count_status_note
            ),
            "badge": "Count now" if item.count_status_key in {"missing", "stale"} else "Review",
            "tone": "alert" if item.count_status_key == "missing" else "warn",
            "href": (
                reverse("stock:edit", args=[item.pk])
                if management_view
                else _stock_workspace_url(q=item.name, focus="uncounted")
            ),
        }
        for item in sorted(
            [
                item
                for item in scoped_items
                if item.count_status_key in {"missing", "stale", "watch"}
            ],
            key=lambda item: (count_priority[item.count_status_key], item.name.lower()),
        )[:4]
    ]

    context = {
        "items": list(page_obj.object_list),
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "filter_query": filter_query,
        "total_items": len(inventory_items),
        "display_item_count": display_item_count,
        "low_stock_count": urgency_counts["critical"] + urgency_counts["low"],
        "critical_stock_count": urgency_counts["critical"],
        "watch_stock_count": urgency_counts["watch"],
        "healthy_stock_count": urgency_counts["healthy"],
        "total_units": total_units,
        "stock_value_estimate": stock_value_estimate,
        "restock_gap_units": restock_gap_units,
        "focus_choices": focus_choices,
        "selected_focus": selected_focus,
        "selected_focus_label": focus_labels.get(selected_focus, ""),
        "missing_count_count": count_status_counts["missing"],
        "stale_count_count": count_status_counts["stale"],
        "watch_count_count": count_status_counts["watch"],
        "recently_restocked_count": recently_restocked_count,
        "supplier_action_rows": supplier_action_rows,
        "count_discipline_rows": count_discipline_rows,
        "focus_zone_cards": focus_zone_cards,
        "category_choices": StockItem.Category.choices,
        "selected_category": selected_category,
        "selected_urgency": selected_urgency,
        "urgency_choices": urgency_choices,
        "query": query,
        "filters_active": filters_active,
        "active_filter_count": sum(
            [
                bool(query),
                bool(selected_focus),
                bool(selected_category),
                selected_urgency != "all",
            ]
        ),
        "selected_category_label": category_labels.get(selected_category, ""),
        "selected_urgency_label": urgency_label_map.get(selected_urgency, "") if selected_urgency != "all" else "",
        "selected_preset_label": next(
            (preset["label"] for preset in filter_presets if preset["active"] and preset["query"]),
            "",
        ),
        "return_path": request.get_full_path(),
        "count_return_path": (
            request.get_full_path()
            if management_view
            else _staff_count_return_url(
                query=query,
                category=selected_category,
                urgency=selected_urgency,
            )
        ),
        "filter_presets": filter_presets,
        "attention_items": attention_items,
        "module_panel": module_panel,
        "module_snapshots": module_snapshots,
    }
    return render(request, "stock/list.html", context)


@management_required
def add_item(request):
    venue = current_venue_or_404(request)
    if request.method == "POST":
        form = StockItemForm(request.POST, venue=venue)
        if form.is_valid():
            item = form.save(commit=False)
            item.venue = venue
            item.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=item,
                summary=f"Created stock item {item.name}",
                details={
                    "category": item.category,
                    "quantity": item.quantity,
                    "minimum_level": item.minimum_level,
                },
            )
            messages.success(request, "Stock item created.")
            return redirect("stock:list")
    else:
        form = StockItemForm(venue=venue)

    return render(
        request,
        "stock/form.html",
        {
            "form": form,
            "page_title": "Add Stock Item",
            "submit_label": "Create Item",
        },
    )


@management_required
def edit_item(request, pk):
    venue = current_venue_or_404(request)
    item = get_object_or_404(StockItem, pk=pk, venue=venue)

    if request.method == "POST":
        form = StockItemForm(request.POST, instance=item, venue=venue)
        if form.is_valid():
            updated_item = form.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.UPDATE,
                target=updated_item,
                summary=f"Updated stock item {updated_item.name}",
                details={
                    "quantity": updated_item.quantity,
                    "minimum_level": updated_item.minimum_level,
                    "is_active": updated_item.is_active,
                },
            )
            messages.success(request, "Stock item updated.")
            return redirect("stock:list")
    else:
        form = StockItemForm(instance=item, venue=venue)

    return render(
        request,
        "stock/form.html",
        {
            "form": form,
            "page_title": f"Edit {item.name}",
            "submit_label": "Save Changes",
            "item": item,
        },
    )


@management_required
def delete_item(request, pk):
    item = get_object_or_404(StockItem, pk=pk, venue=current_venue_or_404(request))

    if request.method == "POST":
        item.is_active = False
        item.save(update_fields=["is_active", "updated_at"])
        record_audit_event(
            request,
            action=AuditEvent.Action.DELETE,
            target=item,
            summary=f"Removed stock item {item.name} from active inventory",
        )
        messages.success(request, "Stock item removed from active inventory.")
        return redirect("stock:list")

    return render(request, "stock/confirm_delete.html", {"item": item})


@active_venue_required
def mark_counted(request, pk):
    item = get_object_or_404(StockItem, pk=pk, venue=current_venue_or_404(request))
    management_view = is_management(request.user, request=request)

    if request.method == "POST":
        item.last_counted_at = timezone.now()
        item.save(update_fields=["last_counted_at", "updated_at"])
        record_audit_event(
            request,
            action=AuditEvent.Action.UPDATE,
            target=item,
            summary=f"Marked stock item {item.name} as counted",
            details={"last_counted_at": timezone.localtime(item.last_counted_at).isoformat()},
        )
        manager_notifications_sent = 0
        if not management_view:
            manager_notifications_sent = send_stock_count_push_notification(item, actor=request.user)

        if not management_view and manager_notifications_sent:
            messages.success(request, f"{item.name} counted and managers notified.")
        elif not management_view:
            messages.success(request, f"{item.name} counted and confirmed.")
        else:
            messages.success(request, f"{item.name} marked as counted.")

    fallback_url = (
        reverse("stock:list")
        if management_view
        else _stock_workspace_url(focus="uncounted")
    )
    return redirect(_safe_next_url(request, fallback_url))
