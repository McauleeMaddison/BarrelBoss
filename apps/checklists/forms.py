from django.contrib.auth import get_user_model
from django import forms

from .models import Checklist


User = get_user_model()


class ChecklistForm(forms.ModelForm):
    def __init__(self, *args, venue=None, **kwargs):
        super().__init__(*args, **kwargs)
        if venue is not None:
            self.fields["assigned_to"].queryset = User.objects.filter(
                venue_memberships__venue=venue,
                venue_memberships__is_active=True,
            ).order_by("username")

    class Meta:
        model = Checklist
        fields = [
            "title",
            "checklist_type",
            "assigned_to",
            "due_date",
            "completed",
            "notes",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
