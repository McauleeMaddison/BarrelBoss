from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_management, management_required
from apps.suppliers.models import Supplier

from .forms import OrderForm, OrderItemFormSet
from .models import Order


def _order_context_base(
    orders_qs, *, request_user_id, selected_status, selected_supplier, management_view
):
    orders = list(orders_qs)
    week_start = timezone.localdate() - timedelta(days=7)

    for order in orders:
        order.can_staff_edit = (
            not management_view
            and order.created_by_id
            and order.created_by_id == request_user_id
            and order.status == Order.Status.DRAFT
        )

    return {
        "orders": orders,
        "order_count": len(orders),
        "awaiting_approval_count": orders_qs.filter(status=Order.Status.DRAFT).count(),
        "pending_count": orders_qs.filter(status=Order.Status.PENDING_DELIVERY).count(),
        "delivered_recent_count": orders_qs.filter(
            status=Order.Status.DELIVERED,
            updated_at__date__gte=week_start,
        ).count(),
        "status_choices": Order.Status.choices,
        "selected_status": selected_status,
        "selected_supplier": selected_supplier,
        "suppliers": Supplier.objects.all(),
        "management_view": management_view,
    }


@login_required
def list_orders(request):
    selected_status = request.GET.get("status", "")
    selected_supplier = request.GET.get("supplier", "")
    management_view = is_management(request.user)

    orders_qs = (
        Order.objects.select_related("supplier", "created_by")
        .annotate(total_lines=Count("items"), total_units=Sum("items__quantity"))
        .all()
    )

    if not management_view:
        orders_qs = orders_qs.filter(created_by=request.user)

    if selected_status and selected_status in Order.Status.values:
        orders_qs = orders_qs.filter(status=selected_status)

    if selected_supplier.isdigit():
        orders_qs = orders_qs.filter(supplier_id=int(selected_supplier))

    orders_qs = orders_qs.order_by("-created_at")

    context = _order_context_base(
        orders_qs,
        request_user_id=request.user.id,
        selected_status=selected_status,
        selected_supplier=selected_supplier,
        management_view=management_view,
    )
    return render(request, "orders/list.html", context)


@login_required
def add_order(request):
    management_view = is_management(request.user)

    if request.method == "POST":
        form = OrderForm(request.POST, is_management=management_view)
        formset = OrderItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.created_by = request.user
            if not management_view:
                order.status = Order.Status.DRAFT
            order.save()

            formset.instance = order
            formset.save()

            success_message = (
                f"Order request {order.reference} submitted for manager approval."
                if not management_view
                else f"Order {order.reference} created."
            )
            messages.success(request, success_message)
            return redirect("orders:list")
    else:
        initial = {}
        if not management_view:
            initial["delivery_date"] = ""
        form = OrderForm(is_management=management_view, initial=initial)
        formset = OrderItemFormSet()

    return render(
        request,
        "orders/form.html",
        {
            "form": form,
            "formset": formset,
            "page_title": "Create Order" if management_view else "Create Stock Order Request",
            "submit_label": "Create Order" if management_view else "Submit Request",
            "management_view": management_view,
        },
    )


@login_required
def edit_order(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=pk)
    management_view = is_management(request.user)

    if not management_view:
        if order.created_by_id != request.user.id or order.status != Order.Status.DRAFT:
            messages.error(request, "You can only edit your own draft order requests.")
            return redirect("orders:list")

    if request.method == "POST":
        form = OrderForm(request.POST, instance=order, is_management=management_view)
        formset = OrderItemFormSet(request.POST, instance=order)

        if form.is_valid() and formset.is_valid():
            updated_order = form.save(commit=False)
            if not management_view:
                updated_order.status = order.status
            updated_order.save()
            formset.save()
            messages.success(request, f"Order {order.reference} updated.")
            return redirect("orders:list")
    else:
        form = OrderForm(instance=order, is_management=management_view)
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
            "management_view": management_view,
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
