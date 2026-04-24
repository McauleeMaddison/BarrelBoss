from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StaffProfile

from .models import AuditEvent
from .services import record_audit_event


class AuditEventServiceTests(TestCase):
    def test_record_audit_event_saves_actor_and_summary(self):
        user = User.objects.create_user(username="audit_user", password="strong-pass-123")
        request = self.client.request().wsgi_request
        request.user = user
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        event = record_audit_event(
            request,
            action=AuditEvent.Action.CREATE,
            summary="Created sample record",
            details={"source": "test"},
        )

        self.assertIsNotNone(event)
        self.assertEqual(AuditEvent.objects.count(), 1)
        saved = AuditEvent.objects.get()
        self.assertEqual(saved.actor, user)
        self.assertEqual(saved.actor_username, "audit_user")
        self.assertEqual(saved.summary, "Created sample record")


class AuditLogPageTests(TestCase):
    def setUp(self):
        self.manager_user = User.objects.create_user(
            username="audit_manager",
            password="strong-pass-123",
        )
        self.manager_user.staff_profile.role = StaffProfile.Role.MANAGER
        self.manager_user.staff_profile.save(update_fields=["role"])

        self.staff_user = User.objects.create_user(
            username="audit_staff",
            password="strong-pass-123",
        )

        for index in range(30):
            AuditEvent.objects.create(
                actor=self.manager_user,
                actor_username=self.manager_user.username,
                actor_role=StaffProfile.Role.MANAGER,
                action=AuditEvent.Action.UPDATE if index % 2 else AuditEvent.Action.CREATE,
                target_model="stock.stockitem",
                target_id=str(index + 1),
                summary=f"Audit event {index + 1}",
                details={},
            )

    def test_management_can_view_paginated_audit_log(self):
        self.client.login(username="audit_manager", password="strong-pass-123")
        response = self.client.get(reverse("audit:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Accountability Trail")
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(response.context["page_obj"].number, 1)

    def test_staff_is_redirected_from_audit_log(self):
        self.client.login(username="audit_staff", password="strong-pass-123")
        response = self.client.get(reverse("audit:list"))

        self.assertRedirects(
            response,
            reverse("dashboard:staff_portal"),
            fetch_redirect_response=False,
        )
