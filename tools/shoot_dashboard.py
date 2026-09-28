"""Headless screenshot of the ETIP dashboard for visual verification.

Logs in with the seeded demo credentials, waits for the overview KPIs and the
project table (with SPI-trend sparklines) to render, and writes full-page PNGs.
All external network requests are aborted so the capture proves the page is
fully offline (self-hosted fonts + vendored Chart.js).
"""

from __future__ import annotations

import glob
import sys

from playwright.sync_api import sync_playwright


def _find_chromium() -> str | None:
    """Locate any pre-installed Chromium binary (revision-agnostic)."""
    for pat in (
        "/opt/pw-browsers/chromium-*/chrome-linux*/chrome",
        "/opt/pw-browsers/chromium-*/chrome-linux*/headless_shell",
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


BASE = "http://127.0.0.1:8000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/etip/dashboard.png"
SLUG = "demo-transformation-co"
EMAIL = "admin@demo.co"
PASSWORD = "Str0ng-Passphrase!1"


def _abort_external(route: object) -> None:
    url = route.request.url  # type: ignore[attr-defined]
    if url.startswith(BASE):
        route.continue_()  # type: ignore[attr-defined]
    else:
        route.abort()  # type: ignore[attr-defined]


def main() -> int:
    with sync_playwright() as p:
        exe = _find_chromium()
        launch: dict[str, object] = {"args": ["--no-sandbox"]}
        if exe:
            launch["executable_path"] = exe
        browser = p.chromium.launch(**launch)  # type: ignore[arg-type]
        page = browser.new_page(viewport={"width": 1440, "height": 1024})
        page.route("**/*", _abort_external)
        page.goto(f"{BASE}/dashboard", wait_until="networkidle")

        page.fill("#slug", SLUG)
        page.fill("#email", EMAIL)
        page.fill("#pass", PASSWORD)
        page.click("button:has-text('Sign in')")

        page.wait_for_selector("#projRows tr", timeout=15000)
        page.wait_for_selector(".kpi .trend .spark", timeout=15000)
        page.wait_for_timeout(1200)  # let chart + sparkline animations settle

        page.screenshot(path=OUT, full_page=True)
        print(f"wrote {OUT}")

        # A tighter crop of just the KPI row + project table for the trend detail.
        detail = sys.argv[2] if len(sys.argv) > 2 else None
        if detail:
            page.screenshot(path=detail, clip={"x": 220, "y": 150, "width": 1220, "height": 720})
            print(f"wrote {detail}")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
