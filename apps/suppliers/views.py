from django.shortcuts import render

from apps.accounts.permissions import management_required


@management_required
def list_suppliers(request):
    suppliers = [
        {"name": "Brewline", "contact": "Siobhan Reed", "phone": "01234 567890", "category": "Barrels"},
        {"name": "Cellar Supply Co", "contact": "Ian Finch", "phone": "02071 222333", "category": "Cleaning"},
    ]
    return render(request, "suppliers/list.html", {"suppliers": suppliers})
