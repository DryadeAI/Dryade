import { test, expect, Page } from "@playwright/test";
import path from "path";

/**
 * NVIDIA Inception Program - Portal Navigation & Form Filling
 *
 * Portal: https://www.nvidia.com/en-us/startups/
 * Status: Rolling (always open)
 * Amount: Up to $100K cloud credits + preferred GPU pricing + DGX Cloud Innovation Lab
 *
 * MANUAL STEP: Create an NVIDIA developer account at https://developer.nvidia.com/
 * before running this script if the form requires authentication.
 *
 * DO NOT submit the application -- this script fills fields for review only.
 */

const SCREENSHOT_DIR = path.resolve(
  __dirname,
  "../../internal-docs/fundraising/trails/screenshots"
);

// Company data from master-facts.md -- single source of truth
const COMPANY_DATA = {
  name: "Dryade SAS",
  website: "https://dryade.ai",
  country: "France",
  yearFounded: "2025",
  employees: "2",
  fundingStage: "Pre-seed",
  email: "contact@dryade.ai",
  founderName: "Marc PARVEAU",
  industry: "Enterprise Software",
  siret: "10167975100012",
  address: "30 Rue D'Assalit, 31500 Toulouse, France",
  description:
    "Self-hosted AI agent orchestration platform for regulated industries",
  nvidiaTech: "DGX Spark, GB10 Grace Blackwell, CUDA, vLLM inference",
  aiUseCase:
    "Dryade is a self-hosted AI agent orchestration platform enabling enterprises to deploy AI agents securely on their own infrastructure. The platform orchestrates agents across 5 frameworks (CrewAI, ADK, LangChain, A2A, LangGraph) with 70+ plugins, cryptographically signed plugin supply chain, and air-gapped deployment capability. We run on NVIDIA DGX Spark with GB10 Grace Blackwell Superchip for local model inference, enabling sovereign AI deployment in classified environments. Privacy is not a nice-to-have -- it is our core architecture principle.",
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

test.describe("NVIDIA Inception Application", () => {
  test("navigate and fill NVIDIA Inception application form", async ({
    page,
  }) => {
    // Step 1: Navigate to NVIDIA Inception landing page
    console.log("Step 1: Navigating to NVIDIA Inception landing page...");
    await page.goto("https://www.nvidia.com/en-us/startups/", {
      waitUntil: "domcontentloaded",
      timeout: 60_000,
    });
    await page.waitForTimeout(3000); // Let dynamic content load
    await screenshotStep(
      page,
      "nvidia-01-landing.png",
      "NVIDIA Inception landing page"
    );

    // Step 2: Look for and click "Apply Now" or "Join" button
    console.log("Step 2: Looking for Apply Now button...");
    const applyClicked =
      (await tryClick(
        page,
        'a:has-text("Apply Now"), button:has-text("Apply Now")'
      )) ||
      (await tryClick(page, 'a:has-text("Join"), button:has-text("Join")')) ||
      (await tryClick(
        page,
        'a:has-text("Get Started"), button:has-text("Get Started")'
      )) ||
      (await tryClick(page, 'a[href*="inception"], a[href*="apply"]'));

    if (applyClicked) {
      await page.waitForTimeout(3000);
      console.log("Apply button clicked, waiting for form...");
    } else {
      console.log(
        "No Apply button found -- portal may require account first"
      );
      // MANUAL STEP: Create NVIDIA developer account at https://developer.nvidia.com/
    }

    await screenshotStep(
      page,
      "nvidia-02-form.png",
      "Application form or login page after clicking Apply"
    );

    // Step 3: Check if we landed on a login page
    const isLoginPage =
      (await page.locator('input[type="email"], input[type="password"]').count()) > 0 ||
      (await page.locator('text="Sign In"').count()) > 0 ||
      (await page.locator('text="Log In"').count()) > 0;

    if (isLoginPage) {
      console.log(
        "LOGIN REQUIRED: Create NVIDIA developer account at https://developer.nvidia.com/ before running"
      );
      await screenshotStep(
        page,
        "nvidia-02-login-required.png",
        "Login page -- account required before form access"
      );
      // Continue to document what we can see
    }

    // Step 4: Attempt to fill form fields (will succeed only if form is accessible)
    console.log("Step 3: Attempting to fill form fields...");

    // Company name
    await tryFill(
      page,
      'input[name*="company"], input[name*="organization"], input[placeholder*="Company"], input[aria-label*="Company"]',
      COMPANY_DATA.name
    );

    // Website
    await tryFill(
      page,
      'input[name*="website"], input[name*="url"], input[placeholder*="Website"], input[type="url"]',
      COMPANY_DATA.website
    );

    // Country
    await trySelect(
      page,
      'select[name*="country"], select[aria-label*="Country"]',
      COMPANY_DATA.country
    );

    // Year founded
    await tryFill(
      page,
      'input[name*="founded"], input[name*="year"], input[placeholder*="Year"]',
      COMPANY_DATA.yearFounded
    );

    // Number of employees
    await tryFill(
      page,
      'input[name*="employee"], input[name*="team_size"], input[placeholder*="employees"]',
      COMPANY_DATA.employees
    );

    // Funding stage
    await trySelect(
      page,
      'select[name*="funding"], select[name*="stage"], select[aria-label*="Funding"]',
      COMPANY_DATA.fundingStage
    );

    // Contact email
    await tryFill(
      page,
      'input[name*="email"], input[type="email"], input[placeholder*="email"]',
      COMPANY_DATA.email
    );

    // Founder name
    await tryFill(
      page,
      'input[name*="founder"], input[name*="contact_name"], input[placeholder*="Name"]',
      COMPANY_DATA.founderName
    );

    // Industry
    await trySelect(
      page,
      'select[name*="industry"], select[aria-label*="Industry"]',
      COMPANY_DATA.industry
    );

    // AI/ML use case description
    await tryFill(
      page,
      'textarea[name*="description"], textarea[name*="use_case"], textarea[placeholder*="description"]',
      COMPANY_DATA.aiUseCase
    );

    // NVIDIA technology used
    await tryFill(
      page,
      'textarea[name*="nvidia"], textarea[name*="technology"], input[name*="nvidia"], input[name*="technology"]',
      COMPANY_DATA.nvidiaTech
    );

    // Company description (short)
    await tryFill(
      page,
      'textarea[name*="company_description"], textarea[name*="about"]',
      COMPANY_DATA.description
    );

    await screenshotStep(
      page,
      "nvidia-03-filled.png",
      "Form after attempting to fill all fields"
    );

    // Final state screenshot
    await screenshotStep(
      page,
      "nvidia-04-final.png",
      "Final state of the page"
    );

    console.log("NVIDIA Inception navigation complete.");
    console.log("DO NOT SUBMIT -- review filled fields before manual submission.");
  });
});
