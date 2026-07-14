from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffProfile
from apps.accounts.testing import VenueScopedTestCase

from .models import Checklist


class ChecklistModelTests(TestCase):
    def test_string_representation(self):
        task = Checklist(
            title="Unlock stock room",
            checklist_type=Checklist.ChecklistType.OPENING,
            due_date=timezone.localdate(),
        )
        self.assertIn("Unlock stock room", str(task))


class ChecklistViewTests(VenueScopedTestCase):
    def setUp(self):
        super().setUp()
        self.staff_user = self.create_user(username="task_staff", password="strong-pass-123")
        self.staff_two = self.create_user(username="task_staff_two", password="strong-pass-123")

        self.manager_user = self.create_user(
            username="task_manager",
            password="strong-pass-123",
            role=StaffProfile.Role.MANAGER,
        )

        self.task_for_staff = Checklist.objects.create(
            venue=self.venue,
            title="Restock fridges",
            checklist_type=Checklist.ChecklistType.OPENING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=timezone.localdate(),
        )
        self.task_for_other = Checklist.objects.create(
            venue=self.venue,
            title="Count till",
            checklist_type=Checklist.ChecklistType.CLOSING,
            assigned_to=self.staff_two,
            created_by=self.manager_user,
            due_date=timezone.localdate() + timedelta(days=1),
        )
        self.overdue_task = Checklist.objects.create(
            venue=self.venue,
            title="Deep clean line",
            checklist_type=Checklist.ChecklistType.CLEANING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=timezone.localdate() - timedelta(days=1),
        )

    def test_checklists_list_requires_login(self):
        response = self.client.get(reverse("checklists:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_staff_sees_only_their_tasks(self):
        self.client.login(username="task_staff", password="strong-pass-123")
        response = self.client.get(reverse("checklists:list"))

        self.assertContains(response, "Task Workspace")
        self.assertContains(response, "Restock fridges")
        self.assertNotContains(response, "Count till")
        self.assertNotContains(response, "Assign task")

    def test_manager_sees_all_tasks(self):
        self.client.login(username="task_manager", password="strong-pass-123")
        response = self.client.get(reverse("checklists:list"))

        self.assertContains(response, "Task Workspace")
        self.assertContains(response, "Restock fridges")
        self.assertContains(response, "Count till")
        self.assertContains(response, "Assign task")

    def test_checklist_context_exposes_filter_summary_and_module_shell(self):
        self.client.login(username="task_manager", password="strong-pass-123")
        response = self.client.get(
            reverse("checklists:list"),
            {
                "q": "Restock",
                "type": Checklist.ChecklistType.OPENING,
                "status": "pending",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["filters_active"])
        self.assertEqual(response.context["active_filter_count"], 3)
        self.assertEqual(response.context["selected_type_label"], "Opening")
        self.assertEqual(response.context["selected_status_label"], "Pending")
        self.assertTrue(response.context["attention_items"])
        self.assertEqual(response.context["module_panel"]["badge"], "Operations Checklist")
        self.assertEqual(len(response.context["module_snapshots"]), 3)

    def test_checklist_context_exposes_signoff_panels_and_return_path(self):
        Checklist.objects.create(
            venue=self.venue,
            title="Signed off cellar clean",
            checklist_type=Checklist.ChecklistType.CLEANING,
            assigned_to=self.staff_user,
            created_by=self.manager_user,
            due_date=timezone.localdate() - timedelta(days=1),
            completed=True,
            completed_at=timezone.now(),
        )

        self.client.login(username="task_manager", password="strong-pass-123")
        response = self.client.get(reverse("checklists:list"), {"status": "pending"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["completion_lane_cards"]), 4)
        self.assertTrue(response.context["signoff_tasks"])
        self.assertTrue(response.context["recent_signoff_rows"])
        self.assertEqual(
            response.context["return_path"],
            f"{reverse('checklists:list')}?status=pending",
        )

    def test_checklist_overdue_preset_filters_queue(self):
        self.client.login(username="task_manager", password="strong-pass-123")
        response = self.client.get(reverse("checklists:list"), {"preset": "overdue"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deep clean line")
        self.assertNotContains(response, "Count till")
        self.assertEqual(response.context["selected_preset_label"], "Overdue")
        self.assertTrue(
            any(
                preset["active"] and preset["key"] == "overdue"
                for preset in response.context["filter_presets"]
            )
        )

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

    def test_toggle_complete_redirects_back_to_filtered_queue(self):
        self.client.login(username="task_staff", password="strong-pass-123")
        next_url = f"{reverse('checklists:list')}?preset=today&status=pending"
        response = self.client.post(
            reverse("checklists:toggle", args=[self.task_for_staff.pk]),
            {"next": next_url},
        )

        self.assertRedirects(response, next_url, fetch_redirect_response=False)

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
