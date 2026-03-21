import { test, expect, Page } from "@playwright/test";
import path from "path";

/**
 * BPI French Tech Emergence (FTE) - Portal Navigation & Documentation
 *
 * Portal: https://www.bpifrance.fr/catalogue-offres/bourse-french-tech-emergence
 * Status: Rolling (no fixed deadline)
 * Amount: Up to EUR 30,000 (non-dilutive grant)
 *
 * IMPORTANT: Application is submitted via local Bpifrance delegation, NOT a centralized
 * online portal. The process starts with an initial meeting with a Bpifrance innovation
 * advisor (charge d'affaires innovation). This script captures the program page and
 * any available contact/application information.
 *
 * MANUAL STEP: Contact local Bpifrance delegation (Toulouse/Occitanie) to schedule
 * an initial meeting with an innovation advisor.
 *
 * DO NOT submit anything -- this script captures information only.
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
  legalRepresentative: "Marc PARVEAU",
  cfo: "Maxime FONTE",
  dateOfIncorporation: "2025",
  employees: "2",
  revenue: "0",
  email: "contact@dryade.ai",
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

test.describe("BPI French Tech Emergence", () => {
  test("navigate and document BPI FTE program page", async ({ page }) => {
    // Step 1: Navigate to BPI FTE program page
    console.log("Step 1: Navigating to BPI FTE program page...");
    await page.goto(
      "https://www.bpifrance.fr/catalogue-offres/bourse-french-tech-emergence",
      {
        waitUntil: "domcontentloaded",
        timeout: 60_000,
      }
    );
    await page.waitForTimeout(3000);

    // Accept cookies if banner appears
    await tryClick(
      page,
      'button:has-text("Accepter"), button:has-text("Accept"), button[id*="cookie"]'
    );
    await page.waitForTimeout(1000);

    await screenshotStep(
      page,
      "bpi-fte-01-landing.png",
      "BPI FTE program landing page"
    );

    // Step 2: Look for application link or "Candidater" button
    console.log("Step 2: Looking for application/candidature link...");
    const candidaterClicked =
      (await tryClick(
        page,
        'a:has-text("Candidater"), button:has-text("Candidater")'
      )) ||
      (await tryClick(
        page,
        'a:has-text("Postuler"), button:has-text("Postuler")'
      )) ||
      (await tryClick(
        page,
        'a:has-text("Deposer"), button:has-text("Deposer")'
      )) ||
      (await tryClick(
        page,
        'a:has-text("En savoir plus"), button:has-text("En savoir plus")'
      ));

    if (candidaterClicked) {
      await page.waitForTimeout(3000);
      console.log("Application link clicked, checking destination...");
    } else {
      console.log(
        "No direct application button found -- process is relationship-based via local Bpifrance office"
      );
    }

    await screenshotStep(
      page,
      "bpi-fte-02-form.png",
      "Page after clicking application link (or landing if no link found)"
    );

    // Step 3: Check if BPI Connect login is required
    const isBpiConnect =
      page.url().includes("connect.bpifrance.fr") ||
      page.url().includes("bpifrance.fr/mon-espace") ||
      (await page
        .locator('text="BPI Connect", text="Mon espace"')
        .count()) > 0;

    if (isBpiConnect) {
      console.log(
        "BPI CONNECT LOGIN REQUIRED: Create account at https://connect.bpifrance.fr before form access"
      );
      await screenshotStep(
        page,
        "bpi-fte-02-login-required.png",
        "BPI Connect login page -- account required for form access"
      );
    }

    // Step 4: Look for contact info for local Bpifrance delegation
    console.log("Step 3: Looking for local delegation contact info...");

    // Navigate to the regional office page for Occitanie/Toulouse
    try {
      // Try to find a "Trouver votre interlocuteur" or regional contact link
      const contactClicked =
        (await tryClick(
          page,
          'a:has-text("interlocuteur"), a:has-text("delegation")'
        )) ||
        (await tryClick(
          page,
          'a:has-text("contact"), a:has-text("nous contacter")'
        ));

      if (contactClicked) {
        await page.waitForTimeout(3000);
        await screenshotStep(
          page,
          "bpi-fte-03-contact.png",
          "Contact info for local Bpifrance delegation"
        );
      } else {
        // Try navigating directly to the Occitanie delegation page
        await page.goto(
          "https://www.bpifrance.fr/contactez-nous",
          {
            waitUntil: "domcontentloaded",
            timeout: 30_000,
          }
        );
        await page.waitForTimeout(2000);
        await screenshotStep(
          page,
          "bpi-fte-03-contact.png",
          "BPI France contact page for finding local delegation"
        );
      }
    } catch (err) {
      console.error("Error navigating to contact info:", err);
      await screenshotStep(
        page,
        "bpi-fte-03-contact.png",
        "Current page state when looking for contact info"
      );
    }

    // Step 5: Capture program eligibility details
    console.log("Step 4: Navigating back to capture program details...");
    try {
      await page.goto(
        "https://www.bpifrance.fr/catalogue-offres/bourse-french-tech-emergence",
        {
          waitUntil: "domcontentloaded",
          timeout: 30_000,
        }
      );
      await page.waitForTimeout(2000);

      // Scroll down to capture full program details
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(1000);
      await screenshotStep(
        page,
        "bpi-fte-04-details.png",
        "Full program details (scrolled)"
      );
    } catch (err) {
      console.error("Error capturing program details:", err);
    }

    console.log("BPI FTE navigation complete.");
    console.log(
      "NEXT STEP: Contact Bpifrance Occitanie delegation to schedule innovation advisor meeting."
    );
    console.log(
      "Application is relationship-based -- no centralized online form."
    );
    console.log(`Company: ${COMPANY_DATA.name}`);
    console.log(`SIRET: ${COMPANY_DATA.siret}`);
    console.log(`Address: ${COMPANY_DATA.address}`);
    console.log(`Legal Representative: ${COMPANY_DATA.legalRepresentative}`);
  });
});
