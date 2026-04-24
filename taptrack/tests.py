from django.test import Client, TestCase, override_settings
from django.urls import reverse


class ErrorPageTests(TestCase):
    @override_settings(DEBUG=False)
    def test_custom_404_page_is_rendered(self):
        response = self.client.get("/definitely-not-a-real-page/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page Not Found", status_code=404)

    @override_settings(DEBUG=False)
    def test_custom_csrf_failure_page_is_rendered(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(reverse("logout"))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Access Denied", status_code=403)
