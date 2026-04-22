from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StaffProfile

from .models import Breakage


class BreakageModelTests(TestCase):
    def test_string_representation(self):
        record = Breakage(item_name="Pint Glass", quantity=2, issue_type=Breakage.IssueType.BROKEN)
        self.assertIn("Pint Glass", str(record))


class BreakageViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="break_staff", password="strong-pass-123")

        self.manager_user = User.objects.create_user(
            username="break_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

    def test_breakages_list_requires_login(self):
        response = self.client.get(reverse("breakages:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_staff_can_log_breakage(self):
        self.client.login(username="break_staff", password="strong-pass-123")
        response = self.client.post(
            reverse("breakages:add"),
            {
                "item_name": "Wine Glass",
                "quantity": 3,
                "issue_type": Breakage.IssueType.BROKEN,
                "notes": "Dropped during service",
            },
        )

        self.assertRedirects(response, reverse("breakages:list"), fetch_redirect_response=False)
        record = Breakage.objects.get(item_name="Wine Glass")
        self.assertEqual(record.reported_by, self.staff_user)

    def test_staff_cannot_delete_breakage(self):
        record = Breakage.objects.create(
            item_name="Tray",
            quantity=1,
            issue_type=Breakage.IssueType.DAMAGED,
            reported_by=self.staff_user,
        )

        self.client.login(username="break_staff", password="strong-pass-123")
        response = self.client.post(reverse("breakages:delete", args=[record.pk]))

        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )
        self.assertTrue(Breakage.objects.filter(pk=record.pk).exists())

    def test_manager_can_delete_breakage(self):
        record = Breakage.objects.create(
            item_name="Bottle Opener",
            quantity=1,
            issue_type=Breakage.IssueType.MISSING,
            reported_by=self.staff_user,
        )

        self.client.login(username="break_manager", password="strong-pass-123")
        response = self.client.post(reverse("breakages:delete", args=[record.pk]))

        self.assertRedirects(response, reverse("breakages:list"), fetch_redirect_response=False)
        self.assertFalse(Breakage.objects.filter(pk=record.pk).exists())

    def test_breakages_search_filter(self):
        Breakage.objects.create(
            item_name="Pint Glass",
            quantity=2,
            issue_type=Breakage.IssueType.BROKEN,
            reported_by=self.staff_user,
        )
        Breakage.objects.create(
            item_name="Cleaning Cloth",
            quantity=1,
            issue_type=Breakage.IssueType.MISSING,
            reported_by=self.staff_user,
        )

        self.client.login(username="break_staff", password="strong-pass-123")
        response = self.client.get(reverse("breakages:list"), {"q": "pint"})

        self.assertContains(response, "Pint Glass")
        self.assertNotContains(response, "Cleaning Cloth")
