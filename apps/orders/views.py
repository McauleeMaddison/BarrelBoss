from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.scoping import current_venue_or_404
from apps.accounts.permissions import active_venue_required, is_management, management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from apps.suppliers.models import Supplier
from taptrack.module_ui import build_module_link, build_module_panel, build_module_snapshot
from taptrack.pagination import build_query_string, paginate_collection

from .forms import OrderForm, OrderItemFormSet
from .models import Order


def _can_edit_order(user, order, *, management_view):
    return (
        management_view
        or (
            order.created_by_id
            and order.created_by_id == user.id
            and order.status == Order.Status.DRAFT
        )
    )


def _order_context_base(
    display_qs,
    page_obj,
    *,
    metrics_qs,
    request_user_id,
    selected_status,
    selected_supplier,
    management_view,
    venue,
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
        "suppliers": Supplier.objects.filter(venue=venue).order_by("name"),
        "management_view": management_view,
    }


@active_venue_required
def list_orders(request):
    venue = current_venue_or_404(request)
    selected_preset = request.GET.get("preset", "")
    selected_status = request.GET.get("status", "")
    selected_supplier = request.GET.get("supplier", "")
    management_view = is_management(request.user, request=request)
    today = timezone.localdate()

    visible_qs = (
        Order.objects.select_related("supplier", "created_by")
        .filter(venue=venue)
    )

    if not management_view:
        visible_qs = visible_qs.filter(created_by=request.user)

    metrics_qs = visible_qs
    display_qs = visible_qs.annotate(total_lines=Count("items"), total_units=Sum("items__quantity"))

    preset_filters = {
        "drafts": {"status": Order.Status.DRAFT},
        "ordered": {"status": Order.Status.ORDERED},
        "pending": {"status": Order.Status.PENDING_DELIVERY},
        "delivered": {"status": Order.Status.DELIVERED},
    }

    if selected_preset == "overdue":
        display_qs = display_qs.filter(
            delivery_date__lt=today,
            status__in=[Order.Status.ORDERED, Order.Status.PENDING_DELIVERY],
        )
    elif selected_preset in preset_filters:
        display_qs = display_qs.filter(**preset_filters[selected_preset])

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
        venue=venue,
    )
    context["pagination_query"] = build_query_string(request)
    status_labels = dict(Order.Status.choices)
    selected_supplier_label = ""
    if selected_supplier.isdigit():
        selected_supplier_label = (
            Supplier.objects.filter(pk=int(selected_supplier))
            .filter(venue=venue)
            .values_list("name", flat=True)
            .first()
            or ""
        )
    filters_active = bool(selected_preset or selected_status or selected_supplier)
    preset_labels = {
        "drafts": "Drafts",
        "ordered": "Ordered",
        "pending": "Pending Delivery",
        "delivered": "Delivered",
        "overdue": "Overdue Delivery",
    }
    filter_presets = [
        {"label": "All Orders", "query": "", "active": not filters_active},
        {"label": "Drafts", "query": "preset=drafts", "active": selected_preset == "drafts" and not selected_status and not selected_supplier},
        {"label": "Ordered", "query": "preset=ordered", "active": selected_preset == "ordered" and not selected_status and not selected_supplier},
        {"label": "Pending Delivery", "query": "preset=pending", "active": selected_preset == "pending" and not selected_status and not selected_supplier},
        {"label": "Overdue", "query": "preset=overdue", "active": selected_preset == "overdue" and not selected_status and not selected_supplier},
        {"label": "Delivered", "query": "preset=delivered", "active": selected_preset == "delivered" and not selected_status and not selected_supplier},
    ]
    attention_items = []
    if context["overdue_delivery_count"]:
        attention_items.append(
            {
                "label": "Overdue deliveries",
                "value": f"{context['overdue_delivery_count']} order(s)",
                "copy": "Expected delivery dates have passed and should be chased or updated.",
                "tone": "alert",
                "action_label": "Open overdue",
                "url_name": "orders:list",
                "query": "preset=overdue",
            }
        )
    if context["stale_draft_count"]:
        attention_items.append(
            {
                "label": "Stale drafts",
                "value": f"{context['stale_draft_count']} request(s)",
                "copy": "Draft requests have been waiting more than 48 hours and need a decision.",
                "tone": "warn",
                "action_label": "Open drafts",
                "url_name": "orders:list",
                "query": "preset=drafts",
            }
        )
    if context["pending_count"]:
        attention_items.append(
            {
                "label": "Pending delivery",
                "value": f"{context['pending_count']} in transit",
                "copy": "Placed orders are on the way and should stay visible until they land in stock.",
                "tone": "neutral",
                "action_label": "Track pending",
                "url_name": "orders:list",
                "query": "preset=pending",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Order pipeline",
                "value": "Queue clear",
                "copy": "No stale drafts or overdue deliveries are currently showing in this view.",
                "tone": "ok",
                "action_label": "Create order" if management_view else "New request",
                "url_name": "orders:add",
            }
        )

    if management_view:
        if context["overdue_delivery_count"]:
            primary_title = "Review overdue deliveries"
            primary_copy = (
                f"{context['overdue_delivery_count']} order(s) have passed their expected delivery date and should be chased or updated first."
            )
            primary_url = f"{reverse('orders:list')}?preset=overdue"
            primary_label = "Open overdue deliveries"
        elif context["awaiting_approval_count"]:
            primary_title = "Clear the draft queue"
            primary_copy = (
                f"{context['awaiting_approval_count']} request(s) are still waiting for approval or a decision."
            )
            primary_url = f"{reverse('orders:list')}?preset=drafts"
            primary_label = "Review draft queue"
        else:
            primary_title = "Create the next order"
            primary_copy = (
                "The urgent queue is clear, so you can add new supplier orders without missing any current blockers."
            )
            primary_url = reverse("orders:add")
            primary_label = "Create order"
        kicker = "Procurement"
        badge = "Manager Queue"
        title = "Keep supplier orders moving without losing the urgent ones."
        copy = "Clear draft bottlenecks, chase late deliveries, and keep the live supplier pipeline easy to work through."
    else:
        if context["awaiting_approval_count"]:
            primary_title = "Finish your draft requests"
            primary_copy = (
                f"{context['awaiting_approval_count']} request(s) are still sitting in draft and can be finished before they slow the queue down."
            )
            primary_url = f"{reverse('orders:list')}?preset=drafts"
            primary_label = "Review drafts"
        elif context["pending_count"]:
            primary_title = "Track incoming delivery"
            primary_copy = (
                f"{context['pending_count']} order(s) are still in flight and should stay visible until the stock lands."
            )
            primary_url = f"{reverse('orders:list')}?preset=pending"
            primary_label = "Track delivery"
        else:
            primary_title = "Raise a stock request"
            primary_copy = (
                "No open blockers are showing, so this is the right moment to send the next supplier request cleanly."
            )
            primary_url = reverse("orders:add")
            primary_label = "Create request"
        kicker = "Request Tracking"
        badge = "My Queue"
        title = "Track requests, delivery follow-through, and what still needs your attention."
        copy = "Submit requests, finish drafts, and keep incoming deliveries visible until they land in stock."

    module_panel = build_module_panel(
        hero_class="orders-hero",
        kicker=kicker,
        badge=badge,
        title=title,
        copy=copy,
        primary_title=primary_title,
        primary_copy=primary_copy,
        primary_url=primary_url,
        primary_label=primary_label,
        utility_links=[
            build_module_link("Create order" if management_view else "New request", reverse("orders:add")),
            build_module_link("Delivered", f"{reverse('orders:list')}?preset=delivered"),
        ],
        toolbar_notes=[
            f"{context['open_order_count']} open",
            f"{context['pending_count']} pending",
            f"{context['total_units_in_view']} units",
        ],
    )
    module_snapshots = [
        build_module_snapshot(
            label="Awaiting approval" if management_view else "Draft requests",
            state=f"{context['stale_draft_count']} stale" if context["stale_draft_count"] else "Working queue",
            tone="warn" if context["stale_draft_count"] else "ok",
            value=context["awaiting_approval_count"],
            copy=(
                "Requests waiting on approval or a decision before they can move into supplier ordering."
                if management_view
                else "Requests you can still review and finish before they move into the approval queue."
            ),
            action_label="Open drafts" if management_view else "Review drafts",
            action_url=f"{reverse('orders:list')}?preset=drafts",
        ),
        build_module_snapshot(
            label="Pending delivery",
            state="In transit",
            tone="neutral",
            value=context["pending_count"],
            copy=(
                "Orders already placed and still waiting to land into stock, which means they need follow-through rather than reordering."
            ),
            action_label="Track pending",
            action_url=f"{reverse('orders:list')}?preset=pending",
        ),
        build_module_snapshot(
            label="Delivery risk",
            state="Late" if context["overdue_delivery_count"] else "On track",
            tone="alert" if context["overdue_delivery_count"] else "ok",
            value=context["overdue_delivery_count"],
            copy=(
                "Orders with delivery dates already passed and still not closed as delivered, which is where supplier friction usually shows up first."
            ),
            action_label="Open overdue" if context["overdue_delivery_count"] else "View pending",
            action_url=(
                f"{reverse('orders:list')}?preset=overdue"
                if context["overdue_delivery_count"]
                else f"{reverse('orders:list')}?preset=pending"
            ),
        ),
    ]
    context.update(
        {
            "filters_active": filters_active,
            "active_filter_count": sum([bool(selected_preset), bool(selected_status), bool(selected_supplier)]),
            "selected_preset": selected_preset,
            "selected_status_label": status_labels.get(selected_status, ""),
            "selected_supplier_label": selected_supplier_label,
            "selected_preset_label": next(
                (preset["label"] for preset in filter_presets if preset["active"] and preset["query"]),
                preset_labels.get(selected_preset, ""),
            ),
            "filter_presets": filter_presets,
            "attention_items": attention_items,
            "module_panel": module_panel,
            "module_snapshots": module_snapshots,
        }
    )
    return render(request, "orders/list.html", context)


@active_venue_required
def add_order(request):
    venue = current_venue_or_404(request)
    management_view = is_management(request.user, request=request)

    if request.method == "POST":
        form = OrderForm(request.POST, is_management=management_view, venue=venue)
        formset = OrderItemFormSet(request.POST, form_kwargs={"venue": venue})

        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.venue = venue
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

            if management_view:
                messages.success(request, f"Order {order.reference} created.")
                return redirect("orders:list")

            messages.success(request, "Stock request sent to management.")
            return redirect("orders:list")
    else:
        initial = {}

        if not management_view:
            initial["delivery_date"] = ""

        form = OrderForm(is_management=management_view, initial=initial, venue=venue)
        formset = OrderItemFormSet(form_kwargs={"venue": venue})

    return render(
        request,
        "orders/form.html",
        {
            "form": form,
            "formset": formset,
            "page_title": (
                "Create supplier order"
                if management_view
                else "Request stock"
            ),
            "submit_label": (
                "Create supplier order"
                if management_view
                else "Send to management"
            ),
            "management_view": management_view,
        },
    )

@active_venue_required
def edit_order(request, pk):
    venue = current_venue_or_404(request)
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=pk, venue=venue)
    management_view = is_management(request.user, request=request)

    if not _can_edit_order(request.user, order, management_view=management_view):
        messages.error(request, "You can only edit your own draft requests.")
        return redirect("orders:list")

    if request.method == "POST":
        form = OrderForm(request.POST, instance=order, is_management=management_view, venue=venue)
        formset = OrderItemFormSet(request.POST, instance=order, form_kwargs={"venue": venue})

        if form.is_valid() and formset.is_valid():
            updated_order = form.save(commit=False)
            if not management_view:
                updated_order.status = Order.Status.DRAFT
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

            messages.success(request, f"Order {updated_order.reference} updated.")
            return redirect("orders:list")
    else:
        form = OrderForm(instance=order, is_management=management_view, venue=venue)
        formset = OrderItemFormSet(instance=order, form_kwargs={"venue": venue})

    return render(
        request,
        "orders/form.html",
        {
            "form": form,
            "formset": formset,
            "page_title": f"Edit {order.reference}",
            "submit_label": "Save changes",
            "order": order,
            "management_view": management_view,
        },
    )

@management_required
def update_order_status(request, pk):
    order = get_object_or_404(Order, pk=pk, venue=current_venue_or_404(request))

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
