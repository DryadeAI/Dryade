"""Capture screenshots of dryade.ai across multiple viewports and pages."""

import json
import os
import time

from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = "/home/dryade/dryade-internal/screenshots"
BASE_URL = "https://dryade.ai"

VIEWPORTS = {
    "mobile": {"width": 375, "height": 812},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1440, "height": 900},
}

PAGES = {
    "homepage": "/",
    "pricing": "/pricing",
    "docs": "/docs",
    "what-is-dryade": "/what-is-dryade",
    "plugins": "/plugins",
}

results = {}

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])

    for vp_name, vp_size in VIEWPORTS.items():
        for page_name, path in PAGES.items():
            url = f"{BASE_URL}{path}"
            fname_atf = f"{page_name}_{vp_name}_atf.png"
            fname_full = f"{page_name}_{vp_name}_full.png"
            path_atf = os.path.join(SCREENSHOTS_DIR, fname_atf)
            path_full = os.path.join(SCREENSHOTS_DIR, fname_full)

            ctx = browser.new_context(
                viewport=vp_size,
                device_scale_factor=2,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
            page = ctx.new_page()

            try:
                resp = page.goto(url, wait_until="networkidle", timeout=30000)
                status = resp.status if resp else "no response"
                # Wait a bit for lazy-loaded content
                page.wait_for_timeout(1500)

                # Above-the-fold screenshot
                page.screenshot(path=path_atf, full_page=False)
                # Full page screenshot
                page.screenshot(path=path_full, full_page=True)

                # Collect page metadata
                title = page.title()
                h1_texts = page.eval_on_selector_all("h1", "els => els.map(e => e.innerText)")
                cta_buttons = page.eval_on_selector_all(
                    "a[href], button",
                    """els => els.filter(e => {
                        const text = e.innerText.toLowerCase();
                        return text.includes('start') || text.includes('try') ||
                               text.includes('get') || text.includes('sign') ||
                               text.includes('download') || text.includes('deploy') ||
                               text.includes('install') || text.includes('free');
                    }).map(e => ({text: e.innerText.trim(), visible: e.offsetParent !== null, rect: e.getBoundingClientRect()}))""",
                )
                # Check horizontal overflow
                h_overflow = page.evaluate(
                    """() => document.documentElement.scrollWidth > document.documentElement.clientWidth"""
                )
                # Check base font size
                base_font = page.evaluate("""() => getComputedStyle(document.body).fontSize""")
                # Check meta description
                meta_desc = page.evaluate("""() => {
                    const m = document.querySelector('meta[name="description"]');
                    return m ? m.content : null;
                }""")

                results[f"{page_name}_{vp_name}"] = {
                    "url": url,
                    "status": status,
                    "title": title,
                    "h1_texts": h1_texts,
                    "cta_buttons": cta_buttons[:5],
                    "horizontal_overflow": h_overflow,
                    "base_font_size": base_font,
                    "meta_description": meta_desc,
                    "atf_screenshot": path_atf,
                    "full_screenshot": path_full,
                }
                print(
                    f"OK  {vp_name:8s} {page_name:20s} status={status} h1={h1_texts[:2]} overflow={h_overflow}"
                )

            except Exception as e:
                results[f"{page_name}_{vp_name}"] = {
                    "url": url,
                    "error": str(e),
                }
                print(f"ERR {vp_name:8s} {page_name:20s} {e}")

            ctx.close()

    browser.close()

# Save results JSON
with open(os.path.join(SCREENSHOTS_DIR, "analysis.json"), "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nDone. {len(results)} captures saved to {SCREENSHOTS_DIR}/")
