#!/usr/bin/env python3
"""Read-only Playwright smoke checks for a deployed BarrelBoss environment."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import expect, sync_playwright
except ImportError as exc:  # pragma: no cover - exercised outside unit tests
    raise SystemExit(
        "Playwright is not installed. Run `pip install -r requirements-dev.txt` "
        "and `playwright install chromium` before using hosted smoke."
    ) from exc


class SmokeFailure(RuntimeError):
    """Raised when a deployed smoke check fails."""


@dataclass(frozen=True)
class Credentials:
    label: str
    username: str
    password: str


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_base_url(value: str) -> str:
    base_url = (value or "").strip().rstrip("/")
    if not base_url:
        raise SmokeFailure(
            "Set SMOKE_BASE_URL or pass --base-url with the deployed BarrelBoss URL."
        )
    if not re.match(r"^https?://", base_url):
        raise SmokeFailure("SMOKE_BASE_URL must begin with http:// or https://.")
    return base_url


def _require_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise SmokeFailure(f"Set {name} before running hosted smoke.")
    return value


def _credentials(prefix: str, label: str) -> Credentials:
    return Credentials(
        label=label,
        username=_require_env(f"{prefix}_USERNAME"),
        password=_require_env(f"{prefix}_PASSWORD"),
    )


def _fetch_json(url: str, label: str) -> dict:
    request = Request(url, headers={"User-Agent": "BarrelBossHostedSmoke/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except HTTPError as exc:
        raise SmokeFailure(f"{label} returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise SmokeFailure(f"{label} could not be reached: {exc.reason}.") from exc
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"{label} did not return valid JSON.") from exc


def _assert_ok_json(base_url: str, path: str, label: str) -> None:
    payload = _fetch_json(f"{base_url}{path}", label)
    if payload.get("status") != "ok":
        raise SmokeFailure(f"{label} reported status={payload.get('status')!r}.")


def _assert_response_ok(response, label: str) -> None:
    if response is None:
        raise SmokeFailure(f"{label} did not return an HTTP response.")
    if not response.ok:
        raise SmokeFailure(f"{label} returned HTTP {response.status}.")


def _login(page, base_url: str, credentials: Credentials) -> None:
    response = page.goto(f"{base_url}/accounts/login/")
    _assert_response_ok(response, f"{credentials.label} login page")
    page.get_by_label("Username").fill(credentials.username)
    page.get_by_label("Password").fill(credentials.password)
    page.get_by_role("button", name="Sign In").click()


def _assert_url(page, pattern: str, label: str) -> None:
    try:
        expect(page).to_have_url(re.compile(pattern))
    except AssertionError as exc:
        raise SmokeFailure(f"{label} landed on unexpected URL: {page.url}") from exc


def _assert_path_loads(page, base_url: str, path: str) -> None:
    response = page.goto(f"{base_url}{path}")
    _assert_response_ok(response, path)
    if not page.url.startswith(f"{base_url}{path}"):
        raise SmokeFailure(f"{path} redirected unexpectedly to {page.url}.")


def _check_password_reset_page(browser, base_url: str) -> None:
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page.set_default_timeout(15000)
    try:
        response = page.goto(f"{base_url}/accounts/password-reset/")
        _assert_response_ok(response, "password reset page")
        expect(page.get_by_role("heading", name="Reset Password")).to_be_visible()
    finally:
        context.close()


def _check_manager_portal(browser, base_url: str, credentials: Credentials) -> None:
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page.set_default_timeout(15000)
    try:
        _login(page, base_url, credentials)
        _assert_url(page, rf"{re.escape(base_url)}/dashboard/management/$", credentials.label)
        expect(page.get_by_role("heading", name="Today")).to_be_visible()

        for path in (
            "/stock/",
            "/orders/",
            "/suppliers/",
            "/checklists/",
            "/shifts/",
            "/sales/",
            "/reports/",
            "/settings/",
        ):
            _assert_path_loads(page, base_url, path)
    finally:
        context.close()


def _check_staff_portal(browser, base_url: str, credentials: Credentials) -> None:
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page.set_default_timeout(15000)
    try:
        _login(page, base_url, credentials)
        _assert_url(page, rf"{re.escape(base_url)}/dashboard/staff/$", credentials.label)
        expect(page.get_by_role("heading", name="Today")).to_be_visible()

        for path in ("/stock/", "/checklists/", "/breakages/", "/shifts/"):
            _assert_path_loads(page, base_url, path)

        for path in ("/suppliers/", "/reports/", "/audit/", "/staff/"):
            response = page.goto(f"{base_url}{path}")
            _assert_response_ok(response, path)
            _assert_url(page, rf"{re.escape(base_url)}/dashboard/staff/$", f"{credentials.label} restricted route")
            expect(page.get_by_text("Access denied", exact=False)).to_be_visible()
    finally:
        context.close()


def _check_landlord_admin(browser, base_url: str, credentials: Credentials) -> None:
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    page = context.new_page()
    page.set_default_timeout(15000)
    try:
        _login(page, base_url, credentials)
        _assert_url(page, rf"{re.escape(base_url)}/dashboard/management/$", credentials.label)

        response = page.goto(f"{base_url}/admin/")
        _assert_response_ok(response, "landlord admin")
        if not page.url.startswith(f"{base_url}/admin/"):
            raise SmokeFailure(f"Landlord admin redirected unexpectedly to {page.url}.")
        expect(
            page.get_by_text(
                re.compile(r"Site administration|Django administration", re.IGNORECASE)
            ).first
        ).to_be_visible()
    finally:
        context.close()


def _check_mobile_dock(browser, base_url: str, credentials: Credentials) -> None:
    context = browser.new_context(
        viewport={"width": 430, "height": 932},
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    page.set_default_timeout(15000)
    try:
        _login(page, base_url, credentials)
        _assert_url(page, rf"{re.escape(base_url)}/dashboard/staff/$", "mobile dock login")

        dock = page.locator(".mobile-dock")
        expect(dock).to_be_visible()

        dock_box = dock.bounding_box()
        if dock_box is None:
            raise SmokeFailure("Mobile dock bounding box could not be measured.")

        dock_center = dock_box["x"] + (dock_box["width"] / 2)
        viewport_center = 430 / 2
        if abs(dock_center - viewport_center) > 24:
            raise SmokeFailure(
                f"Mobile dock is not centered: dock_center={dock_center:.1f}, "
                f"viewport_center={viewport_center:.1f}."
            )
        if dock_box["x"] < 8 or dock_box["x"] + dock_box["width"] > 422:
            raise SmokeFailure("Mobile dock overflows the viewport edges.")

        toggle = page.locator("[data-command-toggle]")
        expect(toggle).to_be_visible()
        toggle.click()

        sheet = page.locator("#mobile-command-sheet")
        expect(sheet).to_have_attribute("aria-hidden", "false")
        expect(sheet.get_by_text("Requests", exact=True)).to_be_visible()
        expect(sheet.get_by_text("Report breakage", exact=True)).to_be_visible()
    finally:
        context.close()


def _run_checks(base_url: str, headless: bool, credentials: Iterable[Credentials]) -> None:
    manager_creds, staff_creds, landlord_creds = credentials

    print(f"Checking health endpoints for {base_url}", flush=True)
    _assert_ok_json(base_url, "/health/live/", "live health")
    _assert_ok_json(base_url, "/health/ready/", "ready health")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            print("Checking password reset page", flush=True)
            _check_password_reset_page(browser, base_url)

            print("Checking manager role routing and module loads", flush=True)
            _check_manager_portal(browser, base_url, manager_creds)

            print("Checking staff role routing and restricted access", flush=True)
            _check_staff_portal(browser, base_url, staff_creds)

            print("Checking landlord admin access", flush=True)
            _check_landlord_admin(browser, base_url, landlord_creds)

            print("Checking mobile dock alignment and actions", flush=True)
            _check_mobile_dock(browser, base_url, staff_creds)
        except PlaywrightError as exc:
            raise SmokeFailure(f"Playwright interaction failed: {exc}") from exc
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run read-only hosted smoke checks against a deployed BarrelBoss app."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("SMOKE_BASE_URL", ""),
        help="Deployed app base URL. Defaults to SMOKE_BASE_URL.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Open a visible browser window instead of headless mode.",
    )
    args = parser.parse_args()

    base_url = _normalize_base_url(args.base_url)
    headless = False if args.headed else _env_flag("SMOKE_HEADLESS", True)
    credentials = (
        _credentials("SMOKE_MANAGER", "manager login"),
        _credentials("SMOKE_STAFF", "staff login"),
        _credentials("SMOKE_LANDLORD", "landlord login"),
    )

    try:
        _run_checks(base_url, headless, credentials)
    except SmokeFailure as exc:
        print(f"Hosted smoke failed: {exc}", file=sys.stderr)
        return 1

    print("Hosted smoke completed successfully.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
