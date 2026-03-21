import { test, expect, Page } from "@playwright/test";
import path from "path";

/**
 * EIC Accelerator 2026 - Portal Navigation & Form Filling
 *
 * Program page: https://eic.ec.europa.eu/eic-funding-opportunities/eic-accelerator_en
 * Application portal: https://ec.europa.eu/info/funding-tenders/opportunities/portal/
 * Status: Open -- accepting Step 2 applications
 * Deadline: July 8, 2026 (Step 2 target) | September 2, 2026 (backup)
 * Amount: Up to EUR 2,500,000 grant + EUR 1,000,000-10,000,000 equity
 *
 * Application is a 3-step process:
 *   Step 1: Short application (~5 pages) -- ~30% pass rate
 *   Step 2: Full application (10-page business plan) -- ~15-20% pass rate
 *   Step 3: Interview (30-min pitch + 30-min Q&A) -- ~40-50% pass rate
 *   Overall success rate: ~4-5%
 *
 * MANUAL STEP: Create EU Login account at https://webgate.ec.europa.eu/cas/
 * for Funding & Tenders Portal access before running this script.
 *
 * DO NOT submit the application -- this script navigates and captures information only.
 */

const SCREENSHOT_DIR = path.resolve(
  __dirname,
  "../../internal-docs/fundraising/trails/screenshots"
);

// Company data from master-facts.md -- single source of truth
const COMPANY_DATA = {
  name: "Dryade SAS",
  siret: "10167975100012",
  address: "30 Rue D'Assalit, 31500 Toulouse, France",
  ceo: "Marc PARVEAU",
  cfo: "Maxime FONTE",
  email: "contact@dryade.ai",
  website: "https://dryade.ai",
  country: "France",
  yearOfIncorporation: "2025",
  employees: "2",
  trl: "7",
  fundingRequest: "2500000",
  // Deadline: July 8, 2026 (target), September 2, 2026 (backup)
  targetDeadline: "2026-07-08",
  backupDeadline: "2026-09-02",
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

async function trySelect(page: Page, selector: string, value: string) {
  try {
    const element = page.locator(selector).first();
    if (await element.isVisible({ timeout: 3000 })) {
      await element.selectOption({ label: value });
      return true;
    }
  } catch {
    // Element not found -- continue
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

test.describe("EIC Accelerator 2026", () => {
  test("navigate EIC program page and EU Funding & Tenders Portal", async ({
    page,
  }) => {
    // Step 1: Navigate to EIC Accelerator program page
    console.log("Step 1: Navigating to EIC Accelerator program page...");
    try {
      await page.goto(
        "https://eic.ec.europa.eu/eic-funding-opportunities/eic-accelerator_en",
        {
          waitUntil: "domcontentloaded",
          timeout: 60_000,
        }
      );
      await page.waitForTimeout(3000);

      // Accept cookies if banner appears
      await tryClick(
        page,
        'button:has-text("Accept"), button:has-text("Accepter"), button[id*="cookie"], button:has-text("I agree")'
      );
      await page.waitForTimeout(1000);

      await screenshotStep(
        page,
        "eic-01-landing.png",
        "EIC Accelerator program page"
      );
    } catch (err) {
      console.error("Error loading EIC program page:", err);
      await screenshotStep(
        page,
        "eic-01-landing.png",
        "EIC page state (may have failed to load)"
      );
    }

    // Step 2: Navigate to EU Funding & Tenders Portal
    console.log("Step 2: Navigating to EU Funding & Tenders Portal...");
    try {
      await page.goto(
        "https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
        {
          waitUntil: "domcontentloaded",
          timeout: 60_000,
        }
      );
      await page.waitForTimeout(3000);

      // Accept cookies if needed
      await tryClick(
        page,
        'button:has-text("Accept"), button:has-text("I agree"), button[id*="cookie"]'
      );
      await page.waitForTimeout(1000);

      await screenshotStep(
        page,
        "eic-02-portal.png",
        "EU Funding & Tenders Portal main page"
      );
    } catch (err) {
      console.error("Error loading EU F&T Portal:", err);
      await screenshotStep(
        page,
        "eic-02-portal.png",
        "EU Portal state (may have failed to load)"
      );
    }

    // Step 3: Search for EIC Accelerator call
    console.log("Step 3: Searching for EIC Accelerator call...");
    try {
      // Try searching for EIC Accelerator in the portal
      const searchFilled =
        (await tryFill(
          page,
          'input[type="search"], input[name*="search"], input[placeholder*="Search"], input[id*="search"]',
          "EIC Accelerator"
        )) ||
        (await tryFill(
          page,
          'input[type="text"]',
          "EIC Accelerator"
        ));

      if (searchFilled) {
        // Press Enter or click search button
        await page.keyboard.press("Enter");
        await page.waitForTimeout(3000);
      }

      // Try direct navigation to EIC calls
      const eicLinkClicked =
        (await tryClick(
          page,
          'a:has-text("EIC Accelerator")'
        )) ||
        (await tryClick(
          page,
          'a:has-text("EIC"), a[href*="eic"]'
        ));

      if (eicLinkClicked) {
        await page.waitForTimeout(3000);
      }

      await screenshotStep(
        page,
        "eic-03-call.png",
        "EIC Accelerator call page or search results"
      );
    } catch (err) {
      console.error("Error searching for EIC call:", err);
      await screenshotStep(
        page,
        "eic-03-call.png",
        "Portal state after search attempt"
      );
    }

    // Step 4: Check if EU Login (ECAS) is required
    console.log("Step 4: Checking for EU Login requirement...");
    try {
      // Try to access the application submission area
      const applyClicked =
        (await tryClick(
          page,
          'a:has-text("Start Submission"), button:has-text("Start Submission")'
        )) ||
        (await tryClick(
          page,
          'a:has-text("Submit proposal"), button:has-text("Submit")'
        )) ||
        (await tryClick(
          page,
          'a:has-text("Apply"), button:has-text("Apply")'
        ));

      if (applyClicked) {
        await page.waitForTimeout(3000);
      }

      const isEuLogin =
        page.url().includes("webgate.ec.europa.eu/cas") ||
        page.url().includes("ecas") ||
        page.url().includes("eu-login") ||
        (await page.locator('text="EU Login"').count()) > 0 ||
        (await page.locator('text="Sign in"').count()) > 0;

      if (isEuLogin) {
        console.log(
          "EU LOGIN REQUIRED: Create EU Login account at https://webgate.ec.europa.eu/cas/ for Funding & Tenders Portal access"
        );
        await screenshotStep(
          page,
          "eic-04-login-required.png",
          "EU Login (ECAS) page -- account required for portal access"
        );
      } else {
        await screenshotStep(
          page,
          "eic-04-login-required.png",
          "Current page state when checking for login requirement"
        );
      }
    } catch (err) {
      console.error("Error checking EU Login:", err);
      await screenshotStep(
        page,
        "eic-04-login-required.png",
        "Page state during login check"
      );
    }

    // Step 5: Attempt to fill form fields (will succeed only if form is accessible)
    console.log("Step 5: Attempting to fill form fields...");
    try {
      // Company name
      await tryFill(
        page,
        'input[name*="company"], input[name*="organisation"], input[name*="applicant"], input[placeholder*="Company"]',
        COMPANY_DATA.name
      );

      // Country
      await trySelect(
        page,
        'select[name*="country"], select[aria-label*="Country"]',
        COMPANY_DATA.country
      );

      // Year of incorporation
      await tryFill(
        page,
        'input[name*="year"], input[name*="incorporation"], input[name*="founded"]',
        COMPANY_DATA.yearOfIncorporation
      );

      // Number of employees
      await tryFill(
        page,
        'input[name*="employee"], input[name*="fte"], input[name*="headcount"]',
        COMPANY_DATA.employees
      );

      // TRL
      await tryFill(
        page,
        'input[name*="trl"], input[name*="TRL"]',
        COMPANY_DATA.trl
      );
      await trySelect(
        page,
        'select[name*="trl"], select[name*="TRL"]',
        `TRL ${COMPANY_DATA.trl}`
      );

      // Funding request (EUR 2,500,000)
      await tryFill(
        page,
        'input[name*="funding"], input[name*="amount"], input[name*="grant"], input[placeholder*="amount"]',
        COMPANY_DATA.fundingRequest
      );

      // Email
      await tryFill(
        page,
        'input[name*="email"], input[type="email"]',
        COMPANY_DATA.email
      );

      // Website
      await tryFill(
        page,
        'input[name*="website"], input[name*="url"], input[type="url"]',
        COMPANY_DATA.website
      );

      await screenshotStep(
        page,
        "eic-05-form.png",
        "Form fields after fill attempt"
      );
    } catch (err) {
      console.error("Error filling form fields:", err);
      await screenshotStep(
        page,
        "eic-05-form.png",
        "Page state during form fill attempt"
      );
    }

    // Step 6: Final screenshot
    await screenshotStep(
      page,
      "eic-06-filled.png",
      "Final state of the page after all navigation and form fill attempts"
    );

    console.log("EIC Accelerator navigation complete.");
    console.log("APPLICATION PROCESS (3 steps):");
    console.log("  Step 1: Short application (~5 pages) -- target deadline July 8, 2026");
    console.log("  Step 2: Full application (if Step 1 passes)");
    console.log("  Step 3: Interview (30-min pitch + 30-min Q&A)");
    console.log(`TARGET DEADLINE: ${COMPANY_DATA.targetDeadline} (July 8, 2026)`);
    console.log(`BACKUP DEADLINE: ${COMPANY_DATA.backupDeadline} (September 2, 2026)`);
    console.log("DO NOT SUBMIT -- review all captured information first.");
    console.log(`Company: ${COMPANY_DATA.name}`);
    console.log(`Funding request: EUR ${COMPANY_DATA.fundingRequest}`);
    console.log(`TRL: ${COMPANY_DATA.trl}`);
  });
});
