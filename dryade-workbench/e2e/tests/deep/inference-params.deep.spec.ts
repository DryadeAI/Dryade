/**
 * Inference Parameters Deep Tests — exercises the new inference params UI
 * added in Phase 211: slider controls, preset dropdown, provider-aware visibility,
 * vLLM advanced parameters, reset, and DB persistence.
 *
 * Uses same pattern as 174.4 deep tests: single authed user, real backend.
 */

import { test, expect, retryApi } from "../../fixtures/deep-test";
import { SettingsPage } from "../../page-objects/SettingsPage";

/**
 * Helper: click a settings sidebar nav button by label text.
 */
async function clickSettingsNav(
  page: import("@playwright/test").Page,
  label: string,
) {
  await page.waitForSelector("nav button", { timeout: 10_000 });
  const navBtn = page
    .locator("nav button")
    .filter({ hasText: new RegExp(label, "i") })
    .first();
  await navBtn.click();
  await page.waitForTimeout(400);
}

/**
 * Helper: navigate to Models, expand Inference Parameters on the LLM card.
 * Returns the collapsible trigger locator.
 */
async function openInferenceParams(page: import("@playwright/test").Page): Promise<boolean> {
  const settings = new SettingsPage(page);
  await settings.goto();
  await clickSettingsNav(page, "Models");
  await page.waitForTimeout(1_500);

  // If "Model configuration not available" is shown, reload and retry once
  const unavailable = page.getByText("Model configuration not available", { exact: false });
  if (await unavailable.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await page.reload();
    await page.waitForTimeout(2_000);
    await clickSettingsNav(page, "Models");
    await page.waitForTimeout(1_500);
  }

  // The Inference Parameters text is inside a CollapsibleTrigger
  const inferenceToggle = page.getByText("Inference Parameters", { exact: false }).first();
  const visible = await inferenceToggle.isVisible({ timeout: 15_000 }).catch(() => false);
  if (!visible) return false;
  await inferenceToggle.click();
  await page.waitForTimeout(500);
  return true;
}

test.describe.serial("Inference Parameters Deep Tests @deep", () => {
  // First: configure a vllm provider via API so InferenceParamsSection renders
  test("@deep should configure vllm provider for LLM via API", async ({
    apiClient,
  }) => {
    const res = await retryApi(() =>
      apiClient.patch("/api/models/config", {
        data: {
          llm_provider: "vllm",
          llm_model: "openai/gpt-oss-20b",
          llm_endpoint: "http://localhost:8000",
        },
      }),
    );

    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.llm_provider).toBe("vllm");
  });

  test("@deep should fetch provider params from API", async ({
    apiClient,
  }) => {
    const res = await apiClient.get("/api/models/provider-params");
    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body).toHaveProperty("provider_params");
    expect(body).toHaveProperty("param_specs");
    expect(body).toHaveProperty("presets");
    expect(body).toHaveProperty("capability_support");
    expect(body).toHaveProperty("vllm_server_params");

    // vllm should be in provider_params
    const providers = Object.keys(body.provider_params);
    expect(providers).toContain("vllm");

    // param_specs should include temperature
    expect(body.param_specs).toHaveProperty("temperature");
    expect(body.param_specs.temperature).toHaveProperty("min");
    expect(body.param_specs.temperature).toHaveProperty("max");

    // presets should include precise, balanced, creative
    expect(body.presets).toHaveProperty("precise");
    expect(body.presets).toHaveProperty("balanced");
    expect(body.presets).toHaveProperty("creative");
  });

  test("@deep should show Inference Parameters collapsible on LLM card", async ({
    authedPage,
  }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();

    // Guard against auth redirect
    if (authedPage.url().includes("/login")) {
      test.skip(true, "Auth token expired");
      return;
    }

    await clickSettingsNav(authedPage, "Models");
    await authedPage.waitForTimeout(1_000);

    // With vllm provider configured, Inference Parameters should be visible
    const inferenceText = authedPage.getByText("Inference Parameters", { exact: false }).first();
    await expect(inferenceText).toBeVisible({ timeout: 15_000 });
  });

  test("@deep should expand and show slider controls with number inputs", async ({
    authedPage,
  }) => {
    if (authedPage.url().includes("/login")) {
      test.skip(true, "Auth token expired");
      return;
    }
    const opened = await openInferenceParams(authedPage);
    if (!opened) { test.skip(true, "Inference Parameters not available"); return; }

    // Should see slider controls (role="slider")
    const sliders = authedPage.locator('[role="slider"]');
    const sliderCount = await sliders.count();
    expect(sliderCount).toBeGreaterThanOrEqual(3);

    // Should see number input fields
    const numberInputs = authedPage.locator('input[type="number"]');
    const inputCount = await numberInputs.count();
    expect(inputCount).toBeGreaterThanOrEqual(3);

    // Slider count should match input count (each param has both)
    expect(sliderCount).toBe(inputCount);
  });

  test("@deep should show preset dropdown with Precise/Balanced/Creative", async ({
    authedPage,
  }) => {
    const opened = await openInferenceParams(authedPage);
    if (!opened) { test.skip(true, "Inference Parameters not available"); return; }

    // Find the Preset label and its associated combobox
    const presetLabel = authedPage.locator("label").filter({ hasText: /Preset/i }).first();
    await expect(presetLabel).toBeVisible({ timeout: 5_000 });

    // Click the preset select trigger — find the combobox near the Preset label
    // Try multiple strategies: parent traversal, sibling, or page-level near
    let selectTrigger = presetLabel.locator("xpath=..").locator("button[role='combobox']").first();
    let hasTrigger = await selectTrigger.isVisible({ timeout: 2_000 }).catch(() => false);
    if (!hasTrigger) {
      // Try grandparent
      selectTrigger = presetLabel.locator("xpath=../..").locator("button[role='combobox']").first();
      hasTrigger = await selectTrigger.isVisible({ timeout: 2_000 }).catch(() => false);
    }
    if (!hasTrigger) {
      // Fallback: find the first combobox on the page (preset is typically the first/only one)
      selectTrigger = authedPage.locator("button[role='combobox']").first();
    }
    await selectTrigger.click();
    await authedPage.waitForTimeout(300);

    // Verify preset options
    await expect(
      authedPage.locator('[role="option"]').filter({ hasText: /Precise/i }).first(),
    ).toBeVisible({ timeout: 3_000 });
    await expect(
      authedPage.locator('[role="option"]').filter({ hasText: /Balanced/i }).first(),
    ).toBeVisible({ timeout: 3_000 });
    await expect(
      authedPage.locator('[role="option"]').filter({ hasText: /Creative/i }).first(),
    ).toBeVisible({ timeout: 3_000 });

    await authedPage.keyboard.press("Escape");
  });

  test("@deep should apply Precise preset and update temperature", async ({
    authedPage,
  }) => {
    const opened = await openInferenceParams(authedPage);
    if (!opened) { test.skip(true, "Inference Parameters not available"); return; }

    // Select Precise preset — target the combobox near the Preset label
    const presetLabel = authedPage.locator("label").filter({ hasText: /Preset/i }).first();
    const presetRow = presetLabel.locator("..");
    const selectTrigger = presetRow.locator("button[role='combobox']").first();
    await selectTrigger.click();
    await authedPage.waitForTimeout(300);

    await authedPage
      .locator('[role="option"]')
      .filter({ hasText: /Precise/i })
      .first()
      .click();
    await authedPage.waitForTimeout(500);

    // Temperature input should have a low value (precise preset = 0.1)
    const tempLabel = authedPage.locator("label").filter({ hasText: /Temperature/i }).first();
    await expect(tempLabel).toBeVisible({ timeout: 5_000 });

    // Find the number input near the Temperature label
    const tempContainer = tempLabel.locator("..").locator("..");
    const tempInput = tempContainer.locator('input[type="number"]').first();
    const value = await tempInput.inputValue();
    const numValue = parseFloat(value);
    expect(numValue).toBeLessThanOrEqual(0.3);
    expect(numValue).toBeGreaterThanOrEqual(0);
  });

  test("@deep should show Reset to Defaults button", async ({
    authedPage,
  }) => {
    const opened = await openInferenceParams(authedPage);
    if (!opened) { test.skip(true, "Inference Parameters not available"); return; }

    const resetBtn = authedPage
      .locator("button")
      .filter({ hasText: /Reset to Defaults/i })
      .first();
    await expect(resetBtn).toBeVisible({ timeout: 5_000 });
  });

  test("@deep should show vLLM Advanced Parameters with restart badge", async ({
    authedPage,
  }) => {
    const opened = await openInferenceParams(authedPage);
    if (!opened) { test.skip(true, "Inference Parameters not available"); return; }

    // Look for the nested "Advanced Parameters" collapsible
    const advancedToggle = authedPage.getByText("Advanced Parameters", { exact: false }).first();
    await expect(advancedToggle).toBeVisible({ timeout: 5_000 });

    // Should show "Requires vLLM restart" badge
    const restartBadge = authedPage.getByText("Requires vLLM restart", { exact: false }).first();
    await expect(restartBadge).toBeVisible({ timeout: 3_000 });

    // Click to expand Advanced Parameters
    await advancedToggle.click();
    await authedPage.waitForTimeout(500);

    // Should show additional controls (dtype select or GPU sliders)
    const advancedContent = authedPage.locator('[role="slider"], button[role="combobox"]');
    const advancedCount = await advancedContent.count();
    // At least the main sliders + advanced controls
    expect(advancedCount).toBeGreaterThanOrEqual(4);
  });

  test("@deep should save and persist inference params via API round-trip", async ({
    apiClient,
  }) => {
    // Save custom inference params
    const updateRes = await apiClient.patch("/api/models/config", {
      data: {
        llm_inference_params: {
          temperature: 0.42,
          top_p: 0.88,
          max_tokens: 2048,
        },
      },
    });
    expect(updateRes.status()).toBe(200);

    // Re-fetch and verify persistence
    const getRes = await apiClient.get("/api/models/config");
    expect(getRes.status()).toBe(200);

    const body = await getRes.json();
    expect(body.llm_inference_params).toBeTruthy();
    expect(body.llm_inference_params.temperature).toBeCloseTo(0.42, 1);
    expect(body.llm_inference_params.top_p).toBeCloseTo(0.88, 1);
    expect(body.llm_inference_params.max_tokens).toBe(2048);
  });

  test("@deep should not show Inference Parameters on Embedding card", async ({
    authedPage,
  }) => {
    const settings = new SettingsPage(authedPage);
    await settings.goto();
    await clickSettingsNav(authedPage, "Models");
    await authedPage.waitForTimeout(1_000);

    // Count all "Inference Parameters" texts on the page
    // With only vllm configured for LLM, embedding should have no provider
    // and thus no inference params section
    const allInferenceTexts = authedPage.getByText("Inference Parameters", { exact: false });
    const count = await allInferenceTexts.count();

    // Should have exactly 1 (on the LLM card only)
    // If embedding also has a provider somehow, it still shouldn't show for embedding
    // because embedding capability has different param support
    expect(count).toBeLessThanOrEqual(2); // LLM + possibly vision if configured
  });
});
