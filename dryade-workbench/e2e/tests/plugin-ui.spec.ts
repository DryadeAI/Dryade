/**
 * Plugin UI E2E tests — Phase 178.2 Task 5.
 *
 * Verifies that plugin UI bundles load in the sandboxed iframe.
 * Requires running backend (core) and frontend (workbench).
 */

import { test, expect, API_URL } from "../fixtures/api";

test.describe("Plugin UI Loading", () => {
  test("should list plugins via API", async ({ apiClient }) => {
    test.setTimeout(90_000);

    // Retry on 429 rate limit (parallel test runs can exhaust rate limits)
    let response;
    for (let attempt = 0; attempt < 5; attempt++) {
      response = await apiClient.get(`${API_URL}/api/plugins`);
      if (response.status() !== 429) break;
      const retryAfter = Number(response.headers()["retry-after"] || "5");
      await new Promise((r) => setTimeout(r, (retryAfter + 1) * 1000));
    }
    if (response!.status() === 429) {
      test.skip(true, "Rate limited after 5 retries — skip in parallel test run");
      return;
    }
    expect(response!.status()).toBe(200);
    const body = await response!.json();
    // Response may be { plugins: [...] } or an array directly
    const plugins = Array.isArray(body) ? body : body.plugins ?? [];
    expect(Array.isArray(plugins)).toBe(true);
  });

  test("should navigate to plugins page", async ({ authedPage }) => {
    await authedPage.goto("/workspace/plugins");
    await authedPage.waitForLoadState("domcontentloaded");
    await expect(authedPage).toHaveURL(/\/workspace\/plugins/);
  });

  test("should render plugin card with UI indicator @plugin", async ({
    authedPage,
    apiClient,
  }) => {
    // Get plugins with UI from API (authenticated)
    const response = await apiClient.get(`${API_URL}/api/plugins`);
    const body = await response.json();
    const plugins = Array.isArray(body) ? body : body.plugins ?? [];
    const uiPlugins = plugins.filter(
      (p: { has_ui?: boolean }) => p.has_ui === true,
    );

    if (uiPlugins.length === 0) {
      test.skip(true, "No plugins with UI loaded — skip iframe test");
      return;
    }

    await authedPage.goto("/workspace/plugins");
    await authedPage.waitForLoadState("domcontentloaded");

    // Verify at least one plugin card is visible
    const pluginCards = authedPage.locator('[data-testid="plugin-card"]');
    await expect(pluginCards.first()).toBeVisible({ timeout: 10000 });
  });

  test("should load plugin UI in sandboxed iframe @plugin", async ({ authedPage, apiClient }) => {
    // Get first plugin with UI
    const response = await apiClient.get(`${API_URL}/api/plugins`);
    const body = await response.json();
    const plugins = Array.isArray(body) ? body : body.plugins ?? [];
    const uiPlugin = plugins.find(
      (p: { has_ui?: boolean }) => p.has_ui === true,
    );

    if (!uiPlugin) {
      test.skip(true, "No plugins with UI loaded — skip iframe test");
      return;
    }

    // Navigate to plugin detail/UI page
    await authedPage.goto(
      `/workspace/plugins/${uiPlugin.name || uiPlugin.plugin_name}`,
    );
    await authedPage.waitForLoadState("domcontentloaded");

    // Find the sandboxed iframe
    const iframe = authedPage.locator("iframe[sandbox]");
    await expect(iframe).toBeVisible({ timeout: 15000 });

    // Verify sandbox attribute restricts capabilities
    const sandbox = await iframe.getAttribute("sandbox");
    expect(sandbox).toBeTruthy();
    // Should NOT have allow-same-origin (prevents XSS escaping sandbox)
    expect(sandbox).not.toContain("allow-same-origin");

    // Verify iframe loaded content (not blank)
    const frame = iframe.contentFrame();
    if (frame) {
      await frame.waitForLoadState("domcontentloaded");
      const body = await frame.locator("body").innerHTML();
      expect(body.length).toBeGreaterThan(0);
    }
  });

  test("should serve UI bundle with correct content-type @plugin", async ({
    apiClient,
  }) => {
    const response = await apiClient.get(`${API_URL}/api/plugins`);
    const body = await response.json();
    const plugins = Array.isArray(body) ? body : body.plugins ?? [];
    const uiPlugin = plugins.find(
      (p: { has_ui?: boolean }) => p.has_ui === true,
    );

    if (!uiPlugin) {
      test.skip(true, "No plugins with UI loaded — skip bundle test");
      return;
    }

    const name = uiPlugin.name || uiPlugin.plugin_name;
    const bundleResponse = await apiClient.get(
      `${API_URL}/api/plugins/${name}/ui/bundle`,
    );
    expect(bundleResponse.status()).toBe(200);
    expect(bundleResponse.headers()["content-type"]).toContain(
      "application/javascript",
    );
    const bundleBody = await bundleResponse.text();
    expect(bundleBody.length).toBeGreaterThan(0);
  });
});
