from datetime import time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffProfile

from .models import Shift


class ShiftModelTests(TestCase):
    def test_duration_handles_overnight_and_break(self):
        shift = Shift(
            staff=User.objects.create_user(username="shift_model_user", password="strong-pass-123"),
            shift_date=timezone.localdate(),
            start_time=time(18, 0),
            end_time=time(1, 0),
            break_minutes=30,
        )

        self.assertEqual(shift.duration_minutes, 390)
        self.assertEqual(shift.duration_hours, 6.5)


class ShiftViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="shift_staff", password="strong-pass-123")
        self.other_staff = User.objects.create_user(username="shift_other", password="strong-pass-123")

        self.manager_user = User.objects.create_user(
            username="shift_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        today = timezone.localdate()

        self.staff_shift = Shift.objects.create(
            staff=self.staff_user,
            shift_date=today,
            start_time=time(16, 0),
            end_time=time(22, 0),
            break_minutes=30,
            notes="Main floor",
            created_by=self.manager_user,
        )
        self.other_shift = Shift.objects.create(
            staff=self.other_staff,
            shift_date=today,
            start_time=time(10, 0),
            end_time=time(14, 0),
            break_minutes=0,
            notes="Cellar delivery",
            created_by=self.manager_user,
        )

    def test_shift_list_requires_login(self):
        response = self.client.get(reverse("shifts:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_staff_sees_only_their_shifts(self):
        self.client.login(username="shift_staff", password="strong-pass-123")
        response = self.client.get(reverse("shifts:list"))

        self.assertContains(response, "Main floor")
        self.assertNotContains(response, "Cellar delivery")
        self.assertEqual(response.context["hours_this_week"], 5.5)

    def test_manager_sees_all_shifts(self):
        self.client.login(username="shift_manager", password="strong-pass-123")
        response = self.client.get(reverse("shifts:list"))

        self.assertContains(response, "Main floor")
        self.assertContains(response, "Cellar delivery")
        self.assertEqual(response.context["total_shifts"], 2)

    def test_manager_can_create_shift(self):
        self.client.login(username="shift_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("shifts:add"),
            {
                "staff": self.staff_user.pk,
                "shift_date": "2026-04-23",
                "start_time": "17:00",
                "end_time": "23:30",
                "break_minutes": "30",
                "notes": "Late service",
            },
        )

        self.assertRedirects(response, reverse("shifts:list"), fetch_redirect_response=False)
        self.assertTrue(Shift.objects.filter(notes="Late service").exists())

    def test_staff_cannot_create_shift(self):
        self.client.login(username="shift_staff", password="strong-pass-123")
        response = self.client.get(reverse("shifts:add"))

        self.assertRedirects(response, reverse("checklists:list"), fetch_redirect_response=False)

    def test_manager_can_delete_shift(self):
        self.client.login(username="shift_manager", password="strong-pass-123")
        response = self.client.post(reverse("shifts:delete", args=[self.staff_shift.pk]))

        self.assertRedirects(response, reverse("shifts:list"), fetch_redirect_response=False)
        self.assertFalse(Shift.objects.filter(pk=self.staff_shift.pk).exists())
