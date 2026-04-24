import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import management_required

from .forms import StockItemForm
from .models import StockItem


@login_required
def list_items(request):
    selected_category = request.GET.get("category", "")
    selected_urgency = request.GET.get("urgency", "all")
    query = (request.GET.get("q") or "").strip()

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

    context = {
        "items": items,
        "total_items": len(inventory_items),
        "display_item_count": len(items),
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
    }
    return render(request, "stock/list.html", context)


@management_required
def add_item(request):
    if request.method == "POST":
        form = StockItemForm(request.POST)
        if form.is_valid():
            form.save()
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
            form.save()
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
        messages.success(request, "Stock item removed from active inventory.")
        return redirect("stock:list")

    return render(request, "stock/confirm_delete.html", {"item": item})
