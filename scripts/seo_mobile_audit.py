"""Mobile & SEO visual audit for dryade.ai"""

import json
import sys

from playwright.sync_api import sync_playwright

BASE = "/home/dryade/dryade-internal/screenshots/seo-audit-2026-03-16"

PAGES = [
    ("homepage", "https://dryade.ai"),
    ("pricing", "https://dryade.ai/pricing"),
    ("enterprise", "https://dryade.ai/enterprise"),
    ("catalog", "https://dryade.ai/catalog"),
]

VIEWPORTS = {
    "desktop": {"width": 1920, "height": 1080},
    "mobile": {"width": 375, "height": 812},
}

def audit_page(page, name, url):
    findings = {}
    viewport_meta = page.evaluate("""() => {
        const meta = document.querySelector('meta[name="viewport"]');
        return meta ? meta.getAttribute('content') : null;
    }""")
    findings["viewport_meta"] = viewport_meta

    small_fonts = page.evaluate("""() => {
        const results = [];
        const els = document.querySelectorAll('body *');
        const seen = new Set();
        for (const el of els) {
            if (!el.offsetParent && el.tagName !== 'BODY' && el.tagName !== 'HTML') continue;
            const style = getComputedStyle(el);
            const size = parseFloat(style.fontSize);
            const text = (el.textContent || '').trim().slice(0, 60);
            if (size < 14 && text.length > 0) {
                const key = el.tagName + ':' + Math.round(size);
                if (!seen.has(key)) {
                    seen.add(key);
                    results.push({tag: el.tagName, fontSize: size, sample: text});
                }
            }
            if (results.length >= 15) break;
        }
        return results;
    }""")
    findings["small_fonts"] = small_fonts

    small_targets = page.evaluate("""() => {
        const results = [];
        const selectors = 'a, button, input, select, textarea, [role="button"], [onclick]';
        const els = document.querySelectorAll(selectors);
        for (const el of els) {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) continue;
            if (rect.width < 48 || rect.height < 48) {
                const text = (el.textContent || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 50);
                results.push({tag: el.tagName, width: Math.round(rect.width), height: Math.round(rect.height), text: text});
            }
            if (results.length >= 20) break;
        }
        return results;
    }""")
    findings["small_touch_targets"] = small_targets

    h_overflow = page.evaluate("""() => {
        return {
            bodyScrollWidth: document.body.scrollWidth,
            windowInnerWidth: window.innerWidth,
            hasOverflow: document.body.scrollWidth > window.innerWidth
        };
    }""")
    findings["horizontal_overflow"] = h_overflow

    atf = page.evaluate("""() => {
        const h1 = document.querySelector('h1');
        const h1Rect = h1 ? h1.getBoundingClientRect() : null;
        const h1Visible = h1Rect ? (h1Rect.top < window.innerHeight && h1Rect.bottom > 0) : false;
        const ctas = [];
        const candidates = document.querySelectorAll('a[href], button');
        for (const el of candidates) {
            const rect = el.getBoundingClientRect();
            if (rect.top > window.innerHeight) continue;
            const text = (el.textContent || '').trim();
            if (text.length > 2 && text.length < 60 && rect.width > 80) {
                ctas.push({text: text.slice(0, 50), top: Math.round(rect.top), visible: rect.top < window.innerHeight && rect.bottom > 0, width: Math.round(rect.width), height: Math.round(rect.height)});
            }
            if (ctas.length >= 8) break;
        }
        return {h1Text: h1 ? h1.textContent.trim().slice(0, 100) : null, h1Visible: h1Visible, h1Top: h1Rect ? Math.round(h1Rect.top) : null, ctasAboveFold: ctas};
    }""")
    findings["above_the_fold"] = atf

    images = page.evaluate("""() => {
        const results = [];
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
            const rect = img.getBoundingClientRect();
            results.push({src: (img.src || '').slice(0, 100), alt: img.alt || '', naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight, displayWidth: Math.round(rect.width), displayHeight: Math.round(rect.height), loading: img.loading || 'eager', hasAlt: !!img.alt});
            if (results.length >= 20) break;
        }
        return results;
    }""")
    findings["images"] = images

    nav = page.evaluate("""() => {
        const nav = document.querySelector('nav, header, [role="navigation"]');
        const hamburger = document.querySelector('[aria-label*="menu"], [aria-label*="Menu"], .hamburger, .menu-toggle, button[class*="menu"], button[class*="nav"]');
        return {hasNav: !!nav, hasHamburger: !!hamburger, hamburgerVisible: hamburger ? hamburger.getBoundingClientRect().width > 0 : false};
    }""")
    findings["navigation"] = nav

    seo = page.evaluate("""() => {
        const title = document.title;
        const desc = document.querySelector('meta[name="description"]');
        const canonical = document.querySelector('link[rel="canonical"]');
        const ogTitle = document.querySelector('meta[property="og:title"]');
        const ogDesc = document.querySelector('meta[property="og:description"]');
        const ogImage = document.querySelector('meta[property="og:image"]');
        return {title: title, description: desc ? desc.content : null, canonical: canonical ? canonical.href : null, ogTitle: ogTitle ? ogTitle.content : null, ogDescription: ogDesc ? ogDesc.content : null, ogImage: ogImage ? ogImage.content : null};
    }""")
    findings["seo_meta"] = seo

    return findings

def main():
    all_results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for page_name, url in PAGES:
            all_results[page_name] = {}
            for vp_name, vp in VIEWPORTS.items():
                print(f"Capturing {page_name} @ {vp_name} ({vp['width']}x{vp['height']})...")
                context = browser.new_context(
                    viewport=vp,
                    user_agent="Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
                    if vp_name == "mobile"
                    else None,
                )
                page = context.new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception as e:
                    print(f"  Warning: {e}")
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    except Exception as e2:
                        print(f"  Failed to load {url}: {e2}")
                        context.close()
                        continue

                path_atf = f"{BASE}/{page_name}-{vp_name}-atf.png"
                page.screenshot(path=path_atf, full_page=False)
                path_full = f"{BASE}/{page_name}-{vp_name}-full.png"
                page.screenshot(path=path_full, full_page=True)

                if vp_name == "mobile":
                    findings = audit_page(page, page_name, url)
                    all_results[page_name] = findings
                context.close()
        browser.close()

    out_path = f"{BASE}/audit-results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {out_path}")

if __name__ == "__main__":
    main()
