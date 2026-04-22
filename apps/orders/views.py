from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import management_required
from apps.suppliers.models import Supplier

from .forms import OrderForm, OrderItemFormSet
from .models import Order


@management_required
def list_orders(request):
    selected_status = request.GET.get("status", "")
    selected_supplier = request.GET.get("supplier", "")

    orders_qs = (
        Order.objects.select_related("supplier", "created_by")
        .annotate(total_lines=Count("items"), total_units=Sum("items__quantity"))
        .all()
    )

    if selected_status and selected_status in Order.Status.values:
        orders_qs = orders_qs.filter(status=selected_status)

    if selected_supplier.isdigit():
        orders_qs = orders_qs.filter(supplier_id=int(selected_supplier))

    orders = list(orders_qs)

    week_start = timezone.localdate() - timedelta(days=7)
    context = {
        "orders": orders,
        "order_count": len(orders),
        "pending_count": Order.objects.filter(status=Order.Status.PENDING_DELIVERY).count(),
        "delivered_recent_count": Order.objects.filter(
            status=Order.Status.DELIVERED,
            updated_at__date__gte=week_start,
        ).count(),
        "status_choices": Order.Status.choices,
        "selected_status": selected_status,
        "selected_supplier": selected_supplier,
        "suppliers": Supplier.objects.all(),
    }
    return render(request, "orders/list.html", context)


@management_required
def add_order(request):
    if request.method == "POST":
        form = OrderForm(request.POST)
        formset = OrderItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.created_by = request.user
            order.save()

            formset.instance = order
            formset.save()

            messages.success(request, f"Order {order.reference} created.")
            return redirect("orders:list")
    else:
        form = OrderForm()
        formset = OrderItemFormSet()

    return render(
        request,
        "orders/form.html",
        {
            "form": form,
            "formset": formset,
            "page_title": "Create Order",
            "submit_label": "Create Order",
        },
    )


@management_required
def edit_order(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=pk)

    if request.method == "POST":
        form = OrderForm(request.POST, instance=order)
        formset = OrderItemFormSet(request.POST, instance=order)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Order {order.reference} updated.")
            return redirect("orders:list")
    else:
        form = OrderForm(instance=order)
        formset = OrderItemFormSet(instance=order)

    return render(
        request,
        "orders/form.html",
        {
            "form": form,
            "formset": formset,
            "page_title": f"Edit {order.reference}",
            "submit_label": "Save Changes",
            "order": order,
        },
    )


@management_required
def update_order_status(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if request.method == "POST":
        new_status = request.POST.get("status", "")
        if new_status in Order.Status.values:
            order.status = new_status
            order.save(update_fields=["status", "updated_at"])
            messages.success(request, f"{order.reference} status updated.")
        else:
            messages.error(request, "Invalid order status.")

    return redirect("orders:list")
