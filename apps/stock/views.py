from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import render

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
