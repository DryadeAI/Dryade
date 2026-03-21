import { test, expect, Page } from "@playwright/test";
import path from "path";

/**
 * BPI Pionniers de l'IA (France 2030) - Portal Navigation & Form Filling
 *
 * Portal: https://www.bpifrance.fr/nos-appels-a-projets-concours/appel-a-projets-des-pionniers-de-lintelligence-artificielle
 * Status: Open -- accepting applications
 * Deadline: June 9, 2026 (next cut-off)
 * Amount: EUR 100,000 - EUR 8,000,000 (Phase 1: EUR 100K-200K target)
 *
 * Entry phase: Phase 1 -- Feasibility (EUR 100,000-200,000)
 * Pre-revenue, no public launch yet = Phase 1 is the most realistic entry point.
 *
 * MANUAL STEP: Create BPI Connect account at https://connect.bpifrance.fr
 * to access the application form.
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
  siret: "10167975100012",
  address: "30 Rue D'Assalit, 31500 Toulouse, France",
  legalRepresentative: "Marc PARVEAU",
  cfo: "Maxime FONTE",
  email: "contact@dryade.ai",
  website: "https://dryade.ai",
  dateOfIncorporation: "2025",
  employees: "2",
  revenue: "0",
};

// Project-specific data for Pionniers IA application
const PROJECT_DATA = {
  title: "Dryade : Plateforme Souveraine d'Orchestration d'Agents IA",
  porteur: "Dryade SAS",
  trlActuel: "7",
  trlVise: "8-9",
  montantDemande: "150000",
  dureeDuProjet: "12 mois",
  // Deadline: June 9, 2026
  deadline: "2026-06-09",
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

test.describe("BPI Pionniers de l'IA (France 2030)", () => {
  test("navigate and fill Pionniers IA application form", async ({ page }) => {
    // Step 1: Navigate to Pionniers IA program page
    console.log("Step 1: Navigating to BPI Pionniers IA program page...");
    await page.goto(
      "https://www.bpifrance.fr/nos-appels-a-projets-concours/appel-a-projets-des-pionniers-de-lintelligence-artificielle",
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
      "pionniers-01-landing.png",
      "BPI Pionniers IA program landing page"
    );

    // Step 2: Look for application link or "Candidater" / "Deposer un dossier" button
    console.log("Step 2: Looking for application/candidature link...");
    const candidaterClicked =
      (await tryClick(
        page,
        'a:has-text("Candidater"), button:has-text("Candidater")'
      )) ||
      (await tryClick(
        page,
        'a:has-text("Deposer"), button:has-text("Deposer")'
      )) ||
      (await tryClick(
        page,
        'a:has-text("Postuler"), button:has-text("Postuler")'
      )) ||
      (await tryClick(
        page,
        'a:has-text("Acceder au formulaire"), button:has-text("Acceder")'
      ));

    if (candidaterClicked) {
      await page.waitForTimeout(3000);
      console.log("Application link clicked, checking destination...");
    } else {
      console.log(
        "No direct application button found on landing page"
      );
    }

    await screenshotStep(
      page,
      "pionniers-02-portal.png",
      "Application portal or page after clicking candidature link"
    );

    // Step 3: Check if BPI Connect login is required
    const isBpiConnect =
      page.url().includes("connect.bpifrance.fr") ||
      page.url().includes("mon-espace") ||
      (await page.locator('text="Connexion", text="Se connecter"').count()) > 0;

    if (isBpiConnect) {
      console.log(
        "BPI CONNECT LOGIN REQUIRED: Create account at https://connect.bpifrance.fr to access application form"
      );
      await screenshotStep(
        page,
        "pionniers-02-login-required.png",
        "BPI Connect login page -- account required for form access"
      );
    }

    // Step 4: Attempt to fill form fields (will succeed only if form is accessible)
    console.log("Step 3: Attempting to fill form fields...");

    // Project title
    await tryFill(
      page,
      'input[name*="titre"], input[name*="title"], input[placeholder*="titre"], input[aria-label*="Titre"]',
      PROJECT_DATA.title
    );

    // Company name / Porteur du projet
    await tryFill(
      page,
      'input[name*="porteur"], input[name*="entreprise"], input[name*="societe"], input[placeholder*="Porteur"]',
      PROJECT_DATA.porteur
    );

    // SIRET
    await tryFill(
      page,
      'input[name*="siret"], input[name*="SIRET"], input[placeholder*="SIRET"]',
      COMPANY_DATA.siret
    );

    // TRL actuel
    await tryFill(
      page,
      'input[name*="trl_actuel"], input[name*="trl"], select[name*="trl"]',
      PROJECT_DATA.trlActuel
    );
    await trySelect(
      page,
      'select[name*="trl_actuel"], select[name*="trl"]',
      `TRL ${PROJECT_DATA.trlActuel}`
    );

    // TRL vise
    await tryFill(
      page,
      'input[name*="trl_vise"], input[name*="trl_target"]',
      PROJECT_DATA.trlVise
    );

    // Montant demande (EUR 150,000)
    await tryFill(
      page,
      'input[name*="montant"], input[name*="amount"], input[placeholder*="montant"]',
      PROJECT_DATA.montantDemande
    );

    // Duree du projet
    await tryFill(
      page,
      'input[name*="duree"], input[name*="duration"], input[placeholder*="duree"]',
      PROJECT_DATA.dureeDuProjet
    );
    await trySelect(
      page,
      'select[name*="duree"], select[name*="duration"]',
      PROJECT_DATA.dureeDuProjet
    );

    // Address
    await tryFill(
      page,
      'input[name*="adresse"], input[name*="address"]',
      COMPANY_DATA.address
    );

    // Legal representative
    await tryFill(
      page,
      'input[name*="representant"], input[name*="dirigeant"]',
      COMPANY_DATA.legalRepresentative
    );

    // Email
    await tryFill(
      page,
      'input[name*="email"], input[type="email"]',
      COMPANY_DATA.email
    );

    // Number of employees
    await tryFill(
      page,
      'input[name*="effectif"], input[name*="employes"], input[name*="salaries"]',
      COMPANY_DATA.employees
    );

    await screenshotStep(
      page,
      "pionniers-03-filled.png",
      "Form after attempting to fill all fields"
    );

    // Step 5: Scroll and capture full program details
    console.log("Step 4: Capturing full program details...");
    try {
      await page.goto(
        "https://www.bpifrance.fr/nos-appels-a-projets-concours/appel-a-projets-des-pionniers-de-lintelligence-artificielle",
        {
          waitUntil: "domcontentloaded",
          timeout: 30_000,
        }
      );
      await page.waitForTimeout(2000);
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(1000);
      await screenshotStep(
        page,
        "pionniers-04-details.png",
        "Full program details (scrolled to bottom)"
      );
    } catch (err) {
      console.error("Error capturing program details:", err);
    }

    console.log("BPI Pionniers IA navigation complete.");
    console.log(`DEADLINE: ${PROJECT_DATA.deadline} (June 9, 2026)`);
    console.log("DO NOT SUBMIT -- review filled fields before manual submission.");
    console.log(`Company: ${COMPANY_DATA.name}`);
    console.log(`SIRET: ${COMPANY_DATA.siret}`);
    console.log(`Project: ${PROJECT_DATA.title}`);
    console.log(`Amount requested: EUR ${PROJECT_DATA.montantDemande}`);
  });
});
