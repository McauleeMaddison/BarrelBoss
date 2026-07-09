from datetime import date, datetime, timedelta

from django import forms

from .models import Shift


class ShiftForm(forms.ModelForm):
    def __init__(self, *args, venue=None, **kwargs):
        super().__init__(*args, **kwargs)
        if venue is not None:
            self.fields["staff"].queryset = self.fields["staff"].queryset.filter(
                venue_memberships__venue=venue,
                venue_memberships__is_active=True,
            ).order_by("username")
            if not self.initial.get("start_time") and venue.default_shift_start_time:
                self.fields["start_time"].initial = venue.default_shift_start_time
            if not self.initial.get("end_time") and venue.default_shift_end_time:
                self.fields["end_time"].initial = venue.default_shift_end_time

    class Meta:
        model = Shift
        fields = [
            "staff",
            "shift_date",
            "start_time",
            "end_time",
            "break_minutes",
            "notes",
        ]
        widgets = {
            "shift_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        break_minutes = cleaned_data.get("break_minutes") or 0

        if not start_time or not end_time:
            return cleaned_data

        start_dt = datetime.combine(date.today(), start_time)
        end_dt = datetime.combine(date.today(), end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        total_minutes = int((end_dt - start_dt).total_seconds() // 60)
        if break_minutes >= total_minutes:
            self.add_error(
                "break_minutes",
                "Break minutes must be shorter than the total shift length.",
            )

        return cleaned_data
