from django import forms

from .models import StockItem


class StockItemForm(forms.ModelForm):
    def __init__(self, *args, venue=None, **kwargs):
        super().__init__(*args, **kwargs)
        if venue is not None:
            self.fields["supplier"].queryset = self.fields["supplier"].queryset.filter(
                venue=venue
            )

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
