from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from taptrack.database_config import build_database_settings, select_database_url


class DatabaseConfigTests(SimpleTestCase):
    def test_select_database_url_uses_primary_url_by_default(self):
        selection = select_database_url(
            {
                "DATABASE_URL": "postgresql://user:password@db.example.com:5432/barrelboss",
            }
        )

        self.assertIsNotNone(selection)
        self.assertEqual(selection.source, "DATABASE_URL")
        self.assertEqual(selection.reason, "primary_database_url")
        self.assertEqual(selection.hostname, "db.example.com")

    def test_select_database_url_uses_fallback_for_render_private_hostname(self):
        selection = select_database_url(
            {
                "DATABASE_URL": "postgresql://user:password@dpg-d85ive6q1p3s73f7o2cg-a:5432/barrelboss",
                "DATABASE_FALLBACK_URL": "postgresql://user:password@db.example.com:5432/barrelboss",
            }
        )

        self.assertIsNotNone(selection)
        self.assertEqual(selection.source, "DATABASE_FALLBACK_URL")
        self.assertEqual(selection.reason, "render_private_hostname")
        self.assertEqual(selection.hostname, "db.example.com")

    def test_select_database_url_uses_external_alias_for_invalid_primary_url(self):
        selection = select_database_url(
            {
                "DATABASE_URL": "dpg-d85ive6q1p3s73f7o2cg-a",
                "RENDER_EXTERNAL_DATABASE_URL": "postgresql://user:password@db.example.com:5432/barrelboss",
            }
        )

        self.assertIsNotNone(selection)
        self.assertEqual(selection.source, "RENDER_EXTERNAL_DATABASE_URL")
        self.assertEqual(selection.reason, "invalid_primary_database_url")
        self.assertEqual(selection.hostname, "db.example.com")

    def test_build_database_settings_defaults_to_sqlite_without_database_env(self):
        databases, selection = build_database_settings(
            Path("/tmp/barrelboss"),
            environ={},
            ssl_require=False,
            connect_timeout=9,
        )

        self.assertIsNone(selection)
        self.assertEqual(databases["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(
            databases["default"]["NAME"],
            Path("/tmp/barrelboss/db.sqlite3"),
        )

    def test_build_database_settings_applies_connect_timeout_to_postgres_urls(self):
        databases, selection = build_database_settings(
            Path("/tmp/barrelboss"),
            environ={
                "DATABASE_URL": "postgresql://user:password@db.example.com:5432/barrelboss",
            },
            ssl_require=True,
            connect_timeout=27,
        )

        self.assertIsNotNone(selection)
        self.assertEqual(databases["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(databases["default"]["HOST"], "db.example.com")
        self.assertEqual(databases["default"]["OPTIONS"]["connect_timeout"], 27)


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
