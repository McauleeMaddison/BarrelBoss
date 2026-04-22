from django import forms

from .models import Breakage


class BreakageForm(forms.ModelForm):
    class Meta:
        model = Breakage
        fields = ["item_name", "quantity", "issue_type", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
