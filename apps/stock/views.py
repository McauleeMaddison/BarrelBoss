from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import management_required

from .forms import StockItemForm
from .models import StockItem


@login_required
def list_items(request):
    selected_category = request.GET.get("category", "")

    items_qs = StockItem.objects.select_related("supplier").filter(is_active=True)

    if selected_category and selected_category in StockItem.Category.values:
        items_qs = items_qs.filter(category=selected_category)

    items = list(items_qs)
    low_stock_count = items_qs.filter(quantity__lte=F("minimum_level")).count()

    context = {
        "items": items,
        "total_items": len(items),
        "low_stock_count": low_stock_count,
        "category_choices": StockItem.Category.choices,
        "selected_category": selected_category,
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
