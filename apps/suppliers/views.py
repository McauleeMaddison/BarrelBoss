from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import management_required

from .forms import SupplierForm
from .models import Supplier


@management_required
def list_suppliers(request):
    query = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "")

    suppliers_qs = Supplier.objects.all()

    if query:
        suppliers_qs = suppliers_qs.filter(
            Q(name__icontains=query)
            | Q(contact_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(email__icontains=query)
        )

    if selected_category and selected_category in Supplier.CategorySupplied.values:
        suppliers_qs = suppliers_qs.filter(category_supplied=selected_category)

    suppliers = list(suppliers_qs)

    context = {
        "suppliers": suppliers,
        "supplier_count": len(suppliers),
        "query": query,
        "category_choices": Supplier.CategorySupplied.choices,
        "selected_category": selected_category,
    }
    return render(request, "suppliers/list.html", context)


@management_required
def add_supplier(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
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
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
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
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == "POST":
        supplier.delete()
        messages.success(request, "Supplier deleted.")
        return redirect("suppliers:list")

    return render(request, "suppliers/confirm_delete.html", {"supplier": supplier})
