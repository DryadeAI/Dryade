import { test, expect, Page } from "@playwright/test";
import path from "path";

/**
 * Dev.to Account Creation - Playwright Script
 *
 * Portal: https://dev.to/enter
 * Purpose: Create a Dryade account for content pipeline (technical articles)
 * Email: contact@dryade.ai
 *
 * IMPORTANT: Dev.to primarily uses OAuth (GitHub, Twitter, etc.) for signup.
 * Email signup may require Forem-specific flow or may redirect to OAuth.
 * If CAPTCHA or OAuth-only blocks automated signup, manual steps are documented below.
 *
 * MANUAL STEPS (if automated signup is blocked):
 * 1. Go to https://dev.to/enter
 * 2. Click "Sign up" or "Create account"
 * 3. Sign up with email: contact@dryade.ai
 * 4. Set username to "dryade" or "dryadeai"
 * 5. Set display name to "Dryade"
 * 6. Complete email verification (check contact@dryade.ai inbox)
 * 7. Set profile bio: "Self-hosted AI agent orchestration. Privacy is not a nice-to-have. https://dryade.ai"
 * 8. Set profile picture to Dryade logo
 *
 * DO NOT run this script without reviewing -- it attempts to create a real account.
 */

const SCREENSHOT_DIR = path.resolve(
  __dirname,
  "../../internal-docs/fundraising/trails/screenshots"
);

const ACCOUNT_DATA = {
  email: "contact@dryade.ai",
  name: "Dryade",
  username: "dryade",
  usernameAlt: "dryadeai",
  bio: "Self-hosted AI agent orchestration platform. Privacy is not a nice-to-have. Your AI, your rules. https://dryade.ai",
  website: "https://dryade.ai",
};

async function screenshotStep(
  page: Page,
  name: string,
  stepDescription: string
) {
  const filePath = path.join(SCREENSHOT_DIR, name);
  try {
    await page.screenshot({ path: filePath, fullPage: true });
    console.log(`Screenshot saved: ${name} -- ${stepDescription}`);
  } catch (err) {
    console.error(`Failed to save screenshot ${name}:`, err);
  }
}

async function tryFill(page: Page, selector: string, value: string) {
  try {
    const element = page.locator(selector).first();
    if (await element.isVisible({ timeout: 3000 })) {
      await element.fill(value);
      return true;
    }
  } catch {
    // Element not found or not visible -- continue
  }
  return false;
}

async function tryClick(page: Page, selector: string) {
  try {
    const element = page.locator(selector).first();
    if (await element.isVisible({ timeout: 5000 })) {
      await element.click();
      return true;
    }
  } catch {
    // Element not found -- continue
  }
  return false;
}

test.describe("Dev.to Account Creation", () => {
  test("navigate to Dev.to signup and attempt account creation", async ({
    page,
  }) => {
    // Step 1: Navigate to Dev.to signup page
    console.log("Step 1: Navigating to Dev.to signup page...");
    await page.goto("https://dev.to/enter", {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });
    await page.waitForTimeout(3000);
    await screenshotStep(
      page,
      "devto-01-signup.png",
      "Dev.to signup/login page"
    );

    // Step 2: Look for email-based signup option
    // Dev.to uses Forem which supports email registration
    console.log("Step 2: Looking for email signup option...");

    // Check if there is a "Create account" or "New user" link/tab
    const hasEmailSignup =
      (await tryClick(
        page,
        'a:has-text("Create account"), button:has-text("Create account")'
      )) ||
      (await tryClick(
        page,
        'a:has-text("Sign Up"), button:has-text("Sign Up")'
      )) ||
      (await tryClick(
        page,
        'a:has-text("New user"), button:has-text("New user")'
      ));

    if (hasEmailSignup) {
      await page.waitForTimeout(2000);
      console.log("Found signup option, navigating...");
    }

    await screenshotStep(
      page,
      "devto-02-signup-options.png",
      "Available signup options"
    );

    // Step 3: Check for CAPTCHA or OAuth-only
    const hasCaptcha =
      (await page.locator('iframe[src*="captcha"], iframe[src*="recaptcha"], iframe[src*="hcaptcha"]').count()) > 0 ||
      (await page.locator('[class*="captcha"], [id*="captcha"]').count()) > 0;

    const hasOAuthOnly =
      (await page.locator('a[href*="github"], a[href*="twitter"], a[href*="apple"]').count()) > 0;

    const hasEmailForm =
      (await page.locator('input[name*="email"], input[type="email"]').count()) > 0;

    if (hasCaptcha) {
      console.log("CAPTCHA DETECTED: Manual signup required.");
      await screenshotStep(
        page,
        "devto-02-captcha-blocked.png",
        "CAPTCHA blocking automated signup"
      );
      // MANUAL STEPS documented in file header
    }

    if (!hasEmailForm && hasOAuthOnly) {
      console.log("OAUTH-ONLY: No email signup form found. Only OAuth providers available.");
      console.log("Available OAuth providers detected on page.");
      await screenshotStep(
        page,
        "devto-02-oauth-only.png",
        "OAuth-only signup -- no email form"
      );
      // MANUAL STEPS:
      // 1. Go to https://dev.to/enter
      // 2. Use GitHub OAuth to sign up (if Dryade GitHub org exists)
      // 3. Or use email magic link if available
      // 4. Set username to "dryade" or "dryadeai"
      // 5. Complete profile setup
    }

    // Step 4: If email form is available, fill it
    if (hasEmailForm) {
      console.log("Step 4: Email signup form found. Filling fields...");

      // Fill email
      await tryFill(
        page,
        'input[name*="email"], input[type="email"], input[placeholder*="email"], input[id*="email"]',
        ACCOUNT_DATA.email
      );

      // Fill name/display name
      await tryFill(
        page,
        'input[name*="name"], input[placeholder*="Name"], input[id*="name"]',
        ACCOUNT_DATA.name
      );

      // Fill username
      await tryFill(
        page,
        'input[name*="username"], input[placeholder*="username"], input[id*="username"]',
        ACCOUNT_DATA.username
      );

      // Fill password if required
      const hasPasswordField =
        (await page.locator('input[type="password"]').count()) > 0;
      if (hasPasswordField) {
        console.log("PASSWORD FIELD DETECTED: Manual password entry required.");
        console.log("DO NOT hardcode passwords in scripts.");
        // MANUAL STEP: Enter a strong password for the contact@dryade.ai account
      }

      await screenshotStep(
        page,
        "devto-02-filled.png",
        "Signup form with fields filled"
      );

      // Step 5: Look for signup submit button (DO NOT auto-click in production)
      const signupButton = page.locator(
        'button[type="submit"]:has-text("Sign"), button:has-text("Create"), button:has-text("Register"), input[type="submit"]'
      ).first();

      if (await signupButton.isVisible({ timeout: 3000 })) {
        console.log("SIGNUP BUTTON FOUND: Ready for manual review before submission.");
        console.log("DO NOT auto-submit -- review filled fields first.");
        // Uncomment below to auto-submit (after human review):
        // await signupButton.click();
        // await page.waitForTimeout(5000);
      }

      await screenshotStep(
        page,
        "devto-03-confirmation.png",
        "Final state before submission"
      );
    } else {
      console.log("No email signup form found on page.");
      console.log("MANUAL STEPS required -- see script header for instructions.");
    }

    // Step 6: Final screenshot of page state
    await screenshotStep(
      page,
      "devto-04-final.png",
      "Final page state"
    );

    console.log("Dev.to account creation script complete.");
    console.log("Review screenshots in internal-docs/fundraising/trails/screenshots/");
  });
});
