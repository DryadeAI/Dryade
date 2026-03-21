"""Visual audit: capture desktop + mobile screenshots of key pages."""

import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = "https://dryade.ai"
OUT = "/home/dryade/dryade-internal/screenshots/visual-audit"

PAGES = {
    "homepage": "/",
    "pricing": "/pricing",
    "about": "/about",
    "enterprise": "/enterprise",
}

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 375, "height": 812},
}

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        results = {}

        for vp_name, vp in VIEWPORTS.items():
            ctx = browser.new_context(
                viewport=vp,
                device_scale_factor=2,
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"
                if vp_name == "mobile"
                else None,
            )
            page = ctx.new_page()

            for page_name, path in PAGES.items():
                url = BASE + path
                fname = f"{page_name}-{vp_name}"
                print(f"Capturing {fname} ...")

                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(1500)

                    # Above-the-fold screenshot
                    page.screenshot(path=os.path.join(OUT, f"{fname}-atf.png"), full_page=False)

                    # Full page screenshot
                    page.screenshot(path=os.path.join(OUT, f"{fname}-full.png"), full_page=True)

                    # Gather page metrics
                    metrics = page.evaluate("""() => {
                        const h1 = document.querySelector('h1');
                        const ctas = Array.from(document.querySelectorAll('a[href], button')).filter(el => {
                            const text = el.textContent.toLowerCase();
                            return text.includes('start') || text.includes('get') || text.includes('try') ||
                                   text.includes('sign') || text.includes('contact') || text.includes('deploy') ||
                                   text.includes('book') || text.includes('download');
                        }).map(el => ({
                            text: el.textContent.trim().substring(0, 60),
                            tag: el.tagName,
                            visible: el.getBoundingClientRect().top < window.innerHeight,
                            top: Math.round(el.getBoundingClientRect().top)
                        }));

                        const images = Array.from(document.querySelectorAll('img')).map(img => ({
                            src: img.src.substring(0, 100),
                            naturalWidth: img.naturalWidth,
                            broken: img.naturalWidth === 0 && img.complete,
                            alt: img.alt || '(none)'
                        }));

                        const fonts = Array.from(document.fonts).map(f => ({
                            family: f.family,
                            status: f.status
                        }));

                        const bodyWidth = document.body.scrollWidth;
                        const viewportWidth = window.innerWidth;
                        const hasHorizontalScroll = bodyWidth > viewportWidth;

                        return {
                            title: document.title,
                            h1: h1 ? h1.textContent.trim() : null,
                            h1_visible_atf: h1 ? h1.getBoundingClientRect().top < window.innerHeight : false,
                            ctas,
                            images,
                            fonts: fonts.slice(0, 10),
                            hasHorizontalScroll,
                            bodyScrollWidth: bodyWidth,
                            viewportWidth,
                            url: window.location.href
                        };
                    }""")
                    results[fname] = metrics

                except Exception as e:
                    print(f"  ERROR: {e}")
                    results[fname] = {"error": str(e)}

            ctx.close()
        browser.close()

    with open(os.path.join(OUT, "metrics.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDone. Screenshots in {OUT}")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
