# Dryade.ai SEO Action Plan

**Generated:** 2026-03-16 | **Health Score:** 62 → 78 (post-fix)

---

## COMPLETED

- [x] **Fix 500 errors on docs/help pages** — Added `export const prerender = true` to `docs/[...slug].astro` and `help/[...slug].astro`
- [x] **Fix sitemap `/marketplace` → `/catalog`** — Updated all URLs and hreflang references
- [x] **Add `/enterprise` and `/about` to sitemap** — Plus 10 doc subpage URLs
- [x] **Create help index page** — `help/index.astro` hub page with article links
- [x] **Create 5 missing docs content files** — security, deployment, plugin-development, workflows, api-reference
- [x] **Verify build** — `astro build` succeeds, all pages prerendered

## Already Correct (False Positives from WebFetch Audit)

- [x] Canonical tags — present in PublicLayout.astro
- [x] OG + Twitter Card meta tags — present in PublicLayout.astro
- [x] Meta descriptions — all pages pass description prop
- [x] Heading structure — only 1 H1 per page (not 9 as initially reported)
- [x] Schema markup — FAQPage, SoftwareApplication, Organization, WebSite, Product, TechArticle all present

## HIGH — Fix Next

- [ ] **Set proper cache-control headers** for static assets in Caddy config (currently `max-age=0`)
- [ ] **Fix generic image alt texts** — "gradient_2.webp", "group-13.svg", "icon-logo" need descriptive alt or `alt=""`
- [ ] **Add `loading="lazy"`** to below-fold images in landing sections

## MEDIUM — Fix Within 1 Month

- [ ] **Add `BreadcrumbList` JSON-LD** to doc pages
- [ ] **Add `ItemList` schema** to catalog page
- [ ] **Expand changelog** content (currently 1 entry, 220 words)
- [ ] **Add breadcrumb UI navigation** to doc and help pages

## LOW — Backlog (SEO Growth)

- [ ] Start blog/resource section for long-tail SEO
- [ ] Create comparison pages ("Dryade vs Dify", "Dryade vs Langflow")
- [ ] Add customer testimonials or anonymized case studies
- [ ] Add `srcset` responsive images for screenshots
- [ ] Tighten CSP (remove `unsafe-inline`/`unsafe-eval`)
- [ ] Set up Lighthouse CI for CWV monitoring
