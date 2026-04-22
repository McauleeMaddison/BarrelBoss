from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffProfile

from .models import Checklist


class ChecklistModelTests(TestCase):
    def test_string_representation(self):
        task = Checklist(
            title="Unlock stock room",
            checklist_type=Checklist.ChecklistType.OPENING,
            due_date=timezone.localdate(),
        )
        self.assertIn("Unlock stock room", str(task))


class ChecklistViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="task_staff", password="strong-pass-123")
        self.staff_two = User.objects.create_user(username="task_staff_two", password="strong-pass-123")

        self.manager_user = User.objects.create_user(
            username="task_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        self.task_for_staff = Checklist.objects.create(
            title="Restock fridges",
            checklist_type=Checklist.ChecklistType.OPENING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=timezone.localdate(),
        )
        self.task_for_other = Checklist.objects.create(
            title="Count till",
            checklist_type=Checklist.ChecklistType.CLOSING,
            assigned_to=self.staff_two,
            created_by=self.manager_user,
            due_date=timezone.localdate() + timedelta(days=1),
        )

    def test_checklists_list_requires_login(self):
        response = self.client.get(reverse("checklists:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_staff_sees_only_their_tasks(self):
        self.client.login(username="task_staff", password="strong-pass-123")
        response = self.client.get(reverse("checklists:list"))

        self.assertContains(response, "Restock fridges")
        self.assertNotContains(response, "Count till")

    def test_manager_sees_all_tasks(self):
        self.client.login(username="task_manager", password="strong-pass-123")
        response = self.client.get(reverse("checklists:list"))

        self.assertContains(response, "Restock fridges")
        self.assertContains(response, "Count till")

    def test_manager_can_create_task(self):
        self.client.login(username="task_manager", password="strong-pass-123")
        response = self.client.post(
            reverse("checklists:add"),
            {
                "title": "Log breakages",
                "checklist_type": Checklist.ChecklistType.CLOSING,
                "assigned_to": self.staff_user.pk,
                "due_date": "2026-04-23",
                "completed": "",
                "notes": "Before final sign-off",
            },
        )

        self.assertRedirects(response, reverse("checklists:list"), fetch_redirect_response=False)
        self.assertTrue(Checklist.objects.filter(title="Log breakages").exists())

    def test_staff_cannot_create_task(self):
        self.client.login(username="task_staff", password="strong-pass-123")
        response = self.client.get(reverse("checklists:add"))
        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )

    def test_staff_can_toggle_their_own_task(self):
        self.client.login(username="task_staff", password="strong-pass-123")
        response = self.client.post(reverse("checklists:toggle", args=[self.task_for_staff.pk]))

        self.assertRedirects(response, reverse("checklists:list"), fetch_redirect_response=False)
        self.task_for_staff.refresh_from_db()
        self.assertTrue(self.task_for_staff.completed)
        self.assertIsNotNone(self.task_for_staff.completed_at)

    def test_staff_cannot_toggle_other_users_task(self):
        self.client.login(username="task_staff", password="strong-pass-123")
        response = self.client.post(reverse("checklists:toggle", args=[self.task_for_other.pk]))

        self.assertRedirects(response, reverse("checklists:list"), fetch_redirect_response=False)
        self.task_for_other.refresh_from_db()
        self.assertFalse(self.task_for_other.completed)

    def test_manager_can_delete_task(self):
        self.client.login(username="task_manager", password="strong-pass-123")
        response = self.client.post(reverse("checklists:delete", args=[self.task_for_staff.pk]))

        self.assertRedirects(response, reverse("checklists:list"), fetch_redirect_response=False)
        self.assertFalse(Checklist.objects.filter(pk=self.task_for_staff.pk).exists())
