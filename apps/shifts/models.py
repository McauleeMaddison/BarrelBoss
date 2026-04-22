from datetime import datetime, timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Shift(models.Model):
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shifts",
    )
    shift_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(720)],
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_shifts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-shift_date", "start_time", "staff__username"]
        indexes = [
            models.Index(fields=["staff", "shift_date"]),
            models.Index(fields=["shift_date"]),
        ]

    def __str__(self):
        return (
            f"{self.staff.username} "
            f"{self.shift_date} {self.start_time.strftime('%H:%M')}"
            f"-{self.end_time.strftime('%H:%M')}"
        )

    @property
    def duration_minutes(self):
        start_dt = datetime.combine(self.shift_date, self.start_time)
        end_dt = datetime.combine(self.shift_date, self.end_time)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        total_minutes = int((end_dt - start_dt).total_seconds() // 60)
        net_minutes = total_minutes - self.break_minutes
        return max(net_minutes, 0)

    @property
    def duration_hours(self):
        return round(self.duration_minutes / 60, 2)
