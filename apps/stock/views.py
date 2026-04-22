from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def list_items(request):
    items = [
        {"name": "Carling 50L", "category": "Beer Barrels", "qty": 3, "unit": "barrels", "threshold": 2},
        {"name": "Jameson", "category": "Spirits", "qty": 5, "unit": "bottles", "threshold": 3},
        {"name": "Coke", "category": "Soft Drinks", "qty": 16, "unit": "cans", "threshold": 12},
    ]
    return render(request, "stock/list.html", {"items": items})
