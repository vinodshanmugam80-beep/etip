"""Screenshots of the single-project scope and the project KPI workspace."""

from __future__ import annotations

import glob
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT_SCOPE = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/etip/project_scope.png"
OUT_WS = sys.argv[2] if len(sys.argv) > 2 else "/home/claude/etip/project_workspace.png"
SLUG, EMAIL, PASSWORD = "demo-transformation-co", "admin@demo.co", "Str0ng-Passphrase!1"


def _chromium() -> str | None:
    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    return hits[-1] if hits else None


def main() -> int:
    with sync_playwright() as p:
        exe = _chromium()
        launch: dict[str, object] = {"args": ["--no-sandbox"]}
        if exe:
            launch["executable_path"] = exe
        browser = p.chromium.launch(**launch)  # type: ignore[arg-type]
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(BASE) else r.abort())
        page.goto(f"{BASE}/dashboard", wait_until="networkidle")
        page.fill("#slug", SLUG)
        page.fill("#email", EMAIL)
        page.fill("#pass", PASSWORD)
        page.click("button:has-text('Sign in')")
        page.wait_for_selector("#projRows tr", timeout=15000)

        # Pick the first Project option in the scope selector and apply it.
        page.evaluate(
            """() => {
                const sel = document.getElementById('scopeSel');
                const opt = Array.from(sel.options).find(o => o.value.startsWith('pj:'));
                if (!opt) return;
                sel.value = opt.value; onScope();
            }"""
        )
        page.wait_for_timeout(1500)
        page.screenshot(path=OUT_SCOPE, full_page=True)
        print(f"wrote {OUT_SCOPE}")

        # Open the workspace by clicking the scoped project's row.
        page.click("#projRows tr")
        page.wait_for_selector("#sheet #pkList", timeout=15000)
        page.wait_for_timeout(900)
        page.screenshot(path=OUT_WS, full_page=True)
        print(f"wrote {OUT_WS}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
