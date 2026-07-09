from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.scoping import current_venue_or_404
from apps.accounts.permissions import management_required
from apps.audit.models import AuditEvent
from apps.audit.services import record_audit_event
from taptrack.pagination import build_query_string, paginate_collection

from .forms import SupplierForm
from .models import Supplier


@management_required
def list_suppliers(request):
    venue = current_venue_or_404(request)
    query = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "")

    suppliers_qs = Supplier.objects.filter(venue=venue)

    if query:
        suppliers_qs = suppliers_qs.filter(
            Q(name__icontains=query)
            | Q(contact_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(email__icontains=query)
        )

    if selected_category and selected_category in Supplier.CategorySupplied.values:
        suppliers_qs = suppliers_qs.filter(category_supplied=selected_category)

    page_obj = paginate_collection(request, suppliers_qs.order_by("name"), per_page=12)
    suppliers = list(page_obj.object_list)
    category_labels = dict(Supplier.CategorySupplied.choices)
    missing_contact_count = suppliers_qs.filter(contact_name="").count()
    missing_phone_count = suppliers_qs.filter(phone="").count()
    missing_email_count = suppliers_qs.filter(email="").count()
    filters_active = bool(query or selected_category)
    filter_presets = [
        {"label": "All Suppliers", "query": "", "active": not filters_active},
        {
            "label": "Beer Barrels",
            "query": "category=BEER_BARRELS",
            "active": selected_category == Supplier.CategorySupplied.BEER_BARRELS and not query,
        },
        {
            "label": "Spirits",
            "query": "category=SPIRITS",
            "active": selected_category == Supplier.CategorySupplied.SPIRITS and not query,
        },
        {
            "label": "Cleaning",
            "query": "category=CLEANING",
            "active": selected_category == Supplier.CategorySupplied.CLEANING and not query,
        },
    ]
    attention_items = []
    if missing_contact_count:
        attention_items.append(
            {
                "label": "Missing contact names",
                "value": f"{missing_contact_count} supplier(s)",
                "copy": "Primary contact names are missing and can slow down call-backs or escalation.",
                "tone": "warn",
                "action_label": "Review directory",
                "url_name": "suppliers:list",
            }
        )
    if missing_phone_count or missing_email_count:
        attention_items.append(
            {
                "label": "Contact gaps",
                "value": f"{missing_phone_count + missing_email_count} missing fields",
                "copy": "Phone and email gaps make ordering fallback and delivery chasing harder.",
                "tone": "alert" if missing_phone_count and missing_email_count else "warn",
                "action_label": "Open suppliers",
                "url_name": "suppliers:list",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "label": "Supplier directory",
                "value": "Contact base healthy",
                "copy": "No obvious supplier contact gaps are visible in the current view.",
                "tone": "ok",
                "action_label": "Create supplier",
                "url_name": "suppliers:add",
            }
        )

    context = {
        "suppliers": suppliers,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_query_string(request),
        "supplier_count": suppliers_qs.count(),
        "query": query,
        "category_choices": Supplier.CategorySupplied.choices,
        "selected_category": selected_category,
        "selected_category_label": category_labels.get(selected_category, ""),
        "filters_active": filters_active,
        "active_filter_count": sum([bool(query), bool(selected_category)]),
        "selected_preset_label": next(
            (preset["label"] for preset in filter_presets if preset["active"] and preset["query"]),
            "",
        ),
        "filter_presets": filter_presets,
        "attention_items": attention_items,
        "hero_signals": [
            {
                "label": "Suppliers in view",
                "value": suppliers_qs.count(),
                "copy": "Live supplier records after applying the current search and category scope.",
                "tone": "neutral",
            },
            {
                "label": "Missing contacts",
                "value": missing_contact_count,
                "copy": "Suppliers without a named contact person in the current directory view.",
                "tone": "warn" if missing_contact_count else "ok",
            },
            {
                "label": "Missing phone or email",
                "value": missing_phone_count + missing_email_count,
                "copy": "Communication gaps still worth cleaning up before the next ordering cycle.",
                "tone": "warn" if missing_phone_count or missing_email_count else "ok",
            },
        ],
    }
    return render(request, "suppliers/list.html", context)


@management_required
def add_supplier(request):
    venue = current_venue_or_404(request)
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.venue = venue
            supplier.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.CREATE,
                target=supplier,
                summary=f"Created supplier {supplier.name}",
                details={"category": supplier.category_supplied},
            )
            messages.success(request, "Supplier created.")
            return redirect("suppliers:list")
    else:
        form = SupplierForm()

    return render(
        request,
        "suppliers/form.html",
        {
            "form": form,
            "page_title": "Add Supplier",
            "submit_label": "Create Supplier",
        },
    )


@management_required
def edit_supplier(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, venue=current_venue_or_404(request))

    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            updated_supplier = form.save()
            record_audit_event(
                request,
                action=AuditEvent.Action.UPDATE,
                target=updated_supplier,
                summary=f"Updated supplier {updated_supplier.name}",
                details={"category": updated_supplier.category_supplied},
            )
            messages.success(request, "Supplier updated.")
            return redirect("suppliers:list")
    else:
        form = SupplierForm(instance=supplier)

    return render(
        request,
        "suppliers/form.html",
        {
            "form": form,
            "page_title": f"Edit {supplier.name}",
            "submit_label": "Save Changes",
            "supplier": supplier,
        },
    )


@management_required
def delete_supplier(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk, venue=current_venue_or_404(request))

    if request.method == "POST":
        supplier_name = supplier.name
        record_audit_event(
            request,
            action=AuditEvent.Action.DELETE,
            target=supplier,
            summary=f"Deleted supplier {supplier_name}",
        )
        supplier.delete()
        messages.success(request, "Supplier deleted.")
        return redirect("suppliers:list")

    return render(request, "suppliers/confirm_delete.html", {"supplier": supplier})
