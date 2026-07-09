import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import is_management, management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from taptrack.pagination import build_query_string, paginate_collection
from taptrack.module_ui import build_module_link, build_module_panel, build_module_snapshot

from .forms import StockItemForm
from .models import StockItem


@login_required
def list_items(request):
    selected_category = request.GET.get("category", "")
    selected_urgency = request.GET.get("urgency", "all")
    query = (request.GET.get("q") or "").strip()
    management_view = is_management(request.user)

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

    items_qs = StockItem.objects.select_related("supplier").filter(is_active=True)

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
    urgency_counts = {key: 0 for key in urgency_labels}
    total_units = 0
    stock_value_estimate = 0
    restock_gap_units = 0

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
        urgency_counts[stock_band] += 1
        if stock_band in {"critical", "low"}:
            restock_gap_units += stock_gap

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
        writer.writerow(["Item", "Category", "Quantity", "Unit", "Minimum", "Stock Gap", "Urgency", "Supplier", "Cost", "Estimated Value"])
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
                    item.supplier.name if item.supplier else "-",
                    f"{item.cost:.2f}",
                    f"{item.value_estimate:.2f}",
                ]
            )
        return response

    page_obj = paginate_collection(request, items, per_page=12)
    filter_query = build_query_string(request, exclude_keys={"export"})
    category_labels = dict(StockItem.Category.choices)
    urgency_label_map = dict(urgency_choices)
    filters_active = bool(query or selected_category or selected_urgency != "all")
    filter_presets = [
        {"label": "All Stock", "query": "", "active": not filters_active},
        {"label": "Critical Risk", "query": "urgency=critical", "active": selected_urgency == "critical" and not query and not selected_category},
        {"label": "Low Stock", "query": "urgency=low", "active": selected_urgency == "low" and not query and not selected_category},
        {"label": "Watch List", "query": "urgency=watch", "active": selected_urgency == "watch" and not query and not selected_category},
        {"label": "Healthy", "query": "urgency=healthy", "active": selected_urgency == "healthy" and not query and not selected_category},
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
            }
        )

    if urgency_counts["critical"]:
        primary_title = "Review critical stock"
        primary_copy = (
            f"{urgency_counts['critical']} line(s) are already out or well below minimum and need attention first."
        )
        primary_url = f"{reverse('stock:list')}?urgency=critical"
        primary_label = "Open critical stock"
    elif urgency_counts["low"]:
        primary_title = "Work the low-stock queue"
        primary_copy = (
            f"{urgency_counts['low']} line(s) are below safe working level and should be queued for replenishment."
        )
        primary_url = f"{reverse('stock:list')}?urgency=low"
        primary_label = "Open low stock"
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
        primary_url = f"{reverse('stock:list')}?urgency=watch"
        primary_label = "Open watch list"

    display_item_count = len(items)
    module_panel = build_module_panel(
        hero_class="inventory-hero",
        kicker="Inventory",
        badge="Stock Control",
        title="Keep service-critical stock visible and actionable.",
        copy=(
            "Use this board to spot urgent shortages fast, tighten replenishment decisions, and keep the working stock list clean."
        ),
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
            f"{restock_gap_units} gap",
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
                f"{reverse('stock:list')}?urgency=critical"
                if urgency_counts["critical"]
                else f"{reverse('stock:list')}?urgency=low"
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
                else f"{reverse('stock:list')}?urgency=low"
            ),
        ),
        build_module_snapshot(
            label="Stable stock",
            state=f"{urgency_counts['healthy']} healthy",
            tone="ok",
            value=urgency_counts["watch"],
            copy=(
                "Lines on the watch list that still have buffer left, but are close enough to need monitoring before they become urgent."
            ),
            action_label="Open watch list",
            action_url=f"{reverse('stock:list')}?urgency=watch",
        ),
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
        "category_choices": StockItem.Category.choices,
        "selected_category": selected_category,
        "selected_urgency": selected_urgency,
        "urgency_choices": urgency_choices,
        "query": query,
        "filters_active": filters_active,
        "active_filter_count": sum(
            [
                bool(query),
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
        "filter_presets": filter_presets,
        "attention_items": attention_items,
        "module_panel": module_panel,
        "module_snapshots": module_snapshots,
    }
    return render(request, "stock/list.html", context)


@management_required
def add_item(request):
    if request.method == "POST":
        form = StockItemForm(request.POST)
        if form.is_valid():
            item = form.save()
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
        form = StockItemForm()

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
    item = get_object_or_404(StockItem, pk=pk)

    if request.method == "POST":
        form = StockItemForm(request.POST, instance=item)
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
        form = StockItemForm(instance=item)

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
    item = get_object_or_404(StockItem, pk=pk)

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
