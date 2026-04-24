from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.permissions import is_management, management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from apps.suppliers.models import Supplier
from taptrack.pagination import build_query_string, paginate_collection

from .forms import OrderForm, OrderItemFormSet
from .models import Order


def _order_context_base(
    display_qs,
    page_obj,
    *,
    metrics_qs,
    request_user_id,
    selected_status,
    selected_supplier,
    management_view,
):
    orders = list(page_obj.object_list)
    week_start = timezone.localdate() - timedelta(days=7)
    today = timezone.localdate()

    status_badge_classes = {
        Order.Status.DRAFT: "badge-status-draft",
        Order.Status.ORDERED: "badge-status-ordered",
        Order.Status.PENDING_DELIVERY: "badge-status-pending",
        Order.Status.DELIVERED: "badge-status-delivered",
        Order.Status.CANCELLED: "badge-status-cancelled",
    }

    for order in orders:
        order.can_staff_edit = (
            not management_view
            and order.created_by_id
            and order.created_by_id == request_user_id
            and order.status == Order.Status.DRAFT
        )
        order.status_badge_class = status_badge_classes.get(order.status, "")
        order.total_units_display = order.total_units or 0
        order.created_by_display = (
            "You"
            if order.created_by_id and order.created_by_id == request_user_id
            else (order.created_by.username if order.created_by else "-")
        )

    draft_count = metrics_qs.filter(status=Order.Status.DRAFT).count()
    ordered_count = metrics_qs.filter(status=Order.Status.ORDERED).count()
    pending_count = metrics_qs.filter(status=Order.Status.PENDING_DELIVERY).count()
    delivered_count = metrics_qs.filter(status=Order.Status.DELIVERED).count()
    cancelled_count = metrics_qs.filter(status=Order.Status.CANCELLED).count()
    open_order_count = draft_count + ordered_count + pending_count
    overdue_delivery_count = metrics_qs.filter(
        delivery_date__lt=today,
        status__in=[Order.Status.ORDERED, Order.Status.PENDING_DELIVERY],
    ).count()
    stale_draft_count = metrics_qs.filter(
        status=Order.Status.DRAFT,
        created_at__date__lte=today - timedelta(days=2),
    ).count()
    total_units_in_view = (
        display_qs.aggregate(total=Sum("items__quantity")).get("total") or 0
    )

    return {
        "orders": orders,
        "order_count": display_qs.count(),
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "awaiting_approval_count": draft_count,
        "pending_count": pending_count,
        "ordered_count": ordered_count,
        "delivered_count": delivered_count,
        "cancelled_count": cancelled_count,
        "open_order_count": open_order_count,
        "overdue_delivery_count": overdue_delivery_count,
        "stale_draft_count": stale_draft_count,
        "total_units_in_view": total_units_in_view,
        "delivered_recent_count": metrics_qs.filter(
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

    visible_qs = (
        Order.objects.select_related("supplier", "created_by")
        .all()
    )

    if not management_view:
        visible_qs = visible_qs.filter(created_by=request.user)

    metrics_qs = visible_qs
    display_qs = visible_qs.annotate(total_lines=Count("items"), total_units=Sum("items__quantity"))

    if selected_status and selected_status in Order.Status.values:
        display_qs = display_qs.filter(status=selected_status)

    if selected_supplier.isdigit():
        display_qs = display_qs.filter(supplier_id=int(selected_supplier))

    display_qs = display_qs.order_by("-created_at")
    page_obj = paginate_collection(request, display_qs, per_page=12)

    context = _order_context_base(
        display_qs,
        page_obj,
        metrics_qs=metrics_qs,
        request_user_id=request.user.id,
        selected_status=selected_status,
        selected_supplier=selected_supplier,
        management_view=management_view,
    )
    context["pagination_query"] = build_query_string(request)
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
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=order,
                summary=f"Created order {order.reference}",
                details={
                    "supplier_id": order.supplier_id,
                    "status": order.status,
                    "item_count": order.items.count(),
                },
            )

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
            record_audit_event(
                request,
                action=AuditEvent.Action.UPDATE,
                target=updated_order,
                summary=f"Updated order {updated_order.reference}",
                details={
                    "status": updated_order.status,
                    "supplier_id": updated_order.supplier_id,
                    "item_count": updated_order.items.count(),
                },
            )
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
            record_audit_event(
                request,
                action=AuditEvent.Action.STATUS,
                target=order,
                summary=f"Updated order {order.reference} status",
                details={"status": new_status},
            )
            messages.success(request, f"{order.reference} status updated.")
        else:
            messages.error(request, "Invalid order status.")

    return redirect("orders:list")
