import { test, expect, Page } from "@playwright/test";
import path from "path";

/**
 * Hashnode Account Creation - Playwright Script
 *
 * Portal: https://hashnode.com/onboard (or https://hashnode.com)
 * Purpose: Create a Dryade publication for content pipeline (technical blog)
 * Email: contact@dryade.ai
 *
 * IMPORTANT: Hashnode primarily uses GitHub OAuth for signup.
 * Email-based signup may be available but is secondary.
 * If CAPTCHA or OAuth-only blocks automated signup, manual steps are documented below.
 *
 * MANUAL STEPS (if automated signup is blocked):
 * 1. Go to https://hashnode.com
 * 2. Click "Start your blog" or "Get Started"
 * 3. Sign up with email: contact@dryade.ai (or GitHub OAuth)
 * 4. Set username/handle to "dryade"
 * 5. Create publication named "Dryade"
 * 6. Set publication tagline: "Self-hosted AI agent orchestration. Your AI, your rules."
 * 7. Complete email verification (check contact@dryade.ai inbox)
 * 8. Set profile/publication picture to Dryade logo
 * 9. Set custom domain later if needed (blog.dryade.ai)
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
  publicationName: "Dryade",
  tagline: "Self-hosted AI agent orchestration. Your AI, your rules.",
  bio: "Self-hosted AI agent orchestration platform with 70+ plugins, post-quantum security, and air-gapped deployment. Privacy is not a nice-to-have. https://dryade.ai",
  website: "https://dryade.ai",
  twitter: "dryadeai",
  github: "DryadeAI",
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

test.describe("Hashnode Account Creation", () => {
  test("navigate to Hashnode signup and attempt account creation", async ({
    page,
  }) => {
    // Step 1: Navigate to Hashnode onboarding page
    console.log("Step 1: Navigating to Hashnode onboarding page...");
    await page.goto("https://hashnode.com/onboard", {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });
    await page.waitForTimeout(3000);
    await screenshotStep(
      page,
      "hashnode-01-signup.png",
      "Hashnode onboarding page"
    );

    // Step 2: Look for signup options
    console.log("Step 2: Looking for signup options...");

    // Hashnode may redirect to main page or show onboarding flow
    const currentUrl = page.url();
    console.log(`Current URL: ${currentUrl}`);

    // If redirected, navigate to main signup
    if (!currentUrl.includes("onboard")) {
      console.log("Redirected from onboard -- trying main page...");
      await page.goto("https://hashnode.com", {
        waitUntil: "domcontentloaded",
        timeout: 60_000,
      });
      await page.waitForTimeout(3000);

      // Look for "Start your blog" or "Get Started" button
      const startClicked =
        (await tryClick(
          page,
          'a:has-text("Start your blog"), button:has-text("Start your blog")'
        )) ||
        (await tryClick(
          page,
          'a:has-text("Get Started"), button:has-text("Get Started")'
        )) ||
        (await tryClick(
          page,
          'a:has-text("Sign Up"), button:has-text("Sign Up")'
        )) ||
        (await tryClick(
          page,
          'a:has-text("Create"), button:has-text("Create")'
        ));

      if (startClicked) {
        await page.waitForTimeout(3000);
        console.log("Found signup entry point...");
      }
    }

    await screenshotStep(
      page,
      "hashnode-02-signup-options.png",
      "Available signup options"
    );

    // Step 3: Check for CAPTCHA or OAuth-only
    const hasCaptcha =
      (await page.locator('iframe[src*="captcha"], iframe[src*="recaptcha"], iframe[src*="hcaptcha"]').count()) > 0 ||
      (await page.locator('[class*="captcha"], [id*="captcha"]').count()) > 0;

    const hasOAuthOnly =
      (await page.locator('a[href*="github.com/login"], button:has-text("GitHub"), a:has-text("Continue with GitHub")').count()) > 0;

    const hasEmailForm =
      (await page.locator('input[name*="email"], input[type="email"]').count()) > 0;

    if (hasCaptcha) {
      console.log("CAPTCHA DETECTED: Manual signup required.");
      await screenshotStep(
        page,
        "hashnode-02-captcha-blocked.png",
        "CAPTCHA blocking automated signup"
      );
      // MANUAL STEPS documented in file header
    }

    if (!hasEmailForm && hasOAuthOnly) {
      console.log("OAUTH-ONLY: No email signup form found. GitHub OAuth available.");
      await screenshotStep(
        page,
        "hashnode-02-oauth-only.png",
        "OAuth-only signup -- GitHub authentication required"
      );
      // MANUAL STEPS:
      // 1. Go to https://hashnode.com
      // 2. Click "Start your blog" or signup button
      // 3. Use GitHub OAuth with DryadeAI organization
      // 4. Or look for email magic link option
      // 5. Set username to "dryade"
      // 6. Create publication "Dryade"
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

      // Fill name
      await tryFill(
        page,
        'input[name*="name"], input[placeholder*="Name"], input[id*="name"]',
        ACCOUNT_DATA.name
      );

      // Fill username/handle
      await tryFill(
        page,
        'input[name*="username"], input[name*="handle"], input[placeholder*="username"], input[placeholder*="handle"]',
        ACCOUNT_DATA.username
      );

      // Fill blog/publication name
      await tryFill(
        page,
        'input[name*="blog"], input[name*="publication"], input[placeholder*="blog"], input[placeholder*="publication"]',
        ACCOUNT_DATA.publicationName
      );

      // Fill tagline
      await tryFill(
        page,
        'input[name*="tagline"], input[placeholder*="tagline"], textarea[name*="tagline"]',
        ACCOUNT_DATA.tagline
      );

      await screenshotStep(
        page,
        "hashnode-02-filled.png",
        "Signup form with fields filled"
      );

      // Step 5: Look for signup submit button (DO NOT auto-click in production)
      const signupButton = page.locator(
        'button[type="submit"]:has-text("Create"), button:has-text("Next"), button:has-text("Continue"), button:has-text("Sign"), input[type="submit"]'
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
        "hashnode-03-confirmation.png",
        "Final state before submission"
      );
    } else {
      console.log("No email signup form found on page.");
      console.log("MANUAL STEPS required -- see script header for instructions.");
    }

    // Step 6: Final screenshot of page state
    await screenshotStep(
      page,
      "hashnode-04-final.png",
      "Final page state"
    );

    console.log("Hashnode account creation script complete.");
    console.log("Review screenshots in internal-docs/fundraising/trails/screenshots/");
    console.log("");
    console.log("POST-CREATION STEPS (after account exists):");
    console.log("1. Create publication named 'Dryade'");
    console.log("2. Set custom domain: blog.dryade.ai (optional)");
    console.log("3. Set publication logo to Dryade branding");
    console.log("4. Configure newsletter settings");
  });
});
