"""Headless screenshot of the Governance (SDLC stage-gate) tab.

Logs in with the seeded demo admin, opens the Governance tab, waits for the gate
tracks to render, and writes a full-page PNG. External requests are aborted so
the capture proves the page renders fully offline.
"""

from __future__ import annotations

import glob
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/etip/governance.png"
SLUG = "demo-transformation-co"
EMAIL = "admin@demo.co"
PASSWORD = "Str0ng-Passphrase!1"


def _find_chromium() -> str | None:
    for pat in (
        "/opt/pw-browsers/chromium-*/chrome-linux*/chrome",
        "/opt/pw-browsers/chromium-*/chrome-linux*/headless_shell",
    ):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def main() -> int:
    with sync_playwright() as p:
        exe = _find_chromium()
        launch: dict[str, object] = {"args": ["--no-sandbox"]}
        if exe:
            launch["executable_path"] = exe
        browser = p.chromium.launch(**launch)  # type: ignore[arg-type]
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.route(
            "**/*",
            lambda r: r.continue_() if r.request.url.startswith(BASE) else r.abort(),
        )
        page.goto(f"{BASE}/dashboard", wait_until="networkidle")

        page.fill("#slug", SLUG)
        page.fill("#email", EMAIL)
        page.fill("#pass", PASSWORD)
        page.click("button:has-text('Sign in')")
        page.wait_for_selector("#projRows tr", timeout=15000)

        page.click(".tab[data-t='governance']")
        page.wait_for_selector(".gate-track .gate", timeout=15000)
        page.wait_for_timeout(900)

        page.screenshot(path=OUT, full_page=True)
        print(f"wrote {OUT}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
