from django.shortcuts import render

from apps.accounts.permissions import management_required


@management_required
def list_orders(request):
    orders = [
        {"ref": "ORD-1001", "supplier": "Brewline", "delivery": "2026-04-23", "status": "Pending Delivery"},
        {"ref": "ORD-1002", "supplier": "Cellar Supply Co", "delivery": "2026-04-25", "status": "Draft"},
    ]
    return render(request, "orders/list.html", {"orders": orders})
