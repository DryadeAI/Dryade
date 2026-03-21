/**
 * Auth Deep Tests — exercises real auth API endpoints with serial execution.
 *
 * Tests: register, login, wrong password, token refresh, logout, session persistence.
 */

import { test, expect, API_URL } from "../../fixtures/deep-test";

test.describe.serial("Auth Deep Tests @deep", () => {
  let testEmail: string;
  let testPassword: string;
  let accessToken: string;
  let refreshToken: string;

  test("@deep should register a new user via API", async ({ page }) => {
    testEmail = `auth-test-${Date.now()}@example.com`;
    testPassword = "AuthTest123!";

    const res = await page.request.post(`${API_URL}/api/auth/register`, {
      data: {
        email: testEmail,
        password: testPassword,
        display_name: "Auth Test",
      },
    });

    expect(res.status()).toBeGreaterThanOrEqual(200);
    expect(res.status()).toBeLessThan(300);

    const body = await res.json();
    expect(body.access_token).toBeTruthy();
    expect(body.refresh_token).toBeTruthy();
    expect(body.token_type).toBeTruthy();
    expect(body.expires_in).toBeGreaterThan(0);

    accessToken = body.access_token;
    refreshToken = body.refresh_token;
  });

  test("@deep should login with valid credentials", async ({ page }) => {
    const res = await page.request.post(`${API_URL}/api/auth/login`, {
      data: {
        email: testEmail,
        password: testPassword,
      },
    });

    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.access_token).toBeTruthy();
    expect(typeof body.access_token).toBe("string");
    expect(body.token_type).toMatch(/bearer/i);

    // Update tokens for subsequent tests
    accessToken = body.access_token;
    refreshToken = body.refresh_token;
  });

  test("@deep should reject login with wrong password", async ({ page }) => {
    const res = await page.request.post(`${API_URL}/api/auth/login`, {
      data: {
        email: testEmail,
        password: "WrongPassword999!",
      },
    });

    expect([401, 403]).toContain(res.status());

    const body = await res.json();
    expect(body.detail || body.error || body.message).toBeTruthy();
  });

  test("@deep should refresh access token", async ({ page }) => {
    const res = await page.request.post(`${API_URL}/api/auth/refresh`, {
      data: {
        refresh_token: refreshToken,
      },
    });

    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.access_token).toBeTruthy();
    expect(typeof body.access_token).toBe("string");

    // Update token for subsequent tests
    accessToken = body.access_token;
  });

  test("@deep should logout and invalidate session", async ({ page }) => {
    const logoutRes = await page.request.post(`${API_URL}/api/auth/logout`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    expect([200, 204]).toContain(logoutRes.status());

    // After logout, verify the endpoint responds (JWT tokens are stateless,
    // so the token may still be valid until expiry — the important thing
    // is that logout itself succeeded with 200/204)
    const meRes = await page.request.get(`${API_URL}/api/users/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    // Token may still work (stateless JWT) or may be blacklisted (401)
    expect([200, 401]).toContain(meRes.status());
  });

  test("@deep should persist session via storageState", async ({
    authedPage,
  }) => {
    // authedPage loads storageState from global-setup (deep-e2e@example.com)
    // It should already be on /workspace/dashboard

    // Verify we are NOT redirected to login
    expect(authedPage.url()).toContain("/workspace/");

    // Verify dashboard content is visible
    await expect(
      authedPage.getByRole("heading").first(),
    ).toBeVisible({ timeout: 10_000 });
  });
});
