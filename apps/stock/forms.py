from django import forms

from .models import StockItem


class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = [
            "name",
            "category",
            "quantity",
            "unit",
            "minimum_level",
            "cost",
            "supplier",
            "last_restocked",
            "notes",
        ]
        widgets = {
            "last_restocked": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
