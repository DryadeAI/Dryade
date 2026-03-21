import type { Page, Locator } from "@playwright/test";

export class AuthPage {
  readonly page: Page;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly submitButton: Locator;
  readonly registerTab: Locator;
  readonly loginTab: Locator;

  constructor(page: Page) {
    this.page = page;
    // Prefer data-testid selectors (added phase 216-03), fallback to role/type selectors
    this.emailInput = page.getByTestId("auth-login-email").or(
      page.getByRole("textbox", { name: /email/i })
    ).first();
    this.passwordInput = page.getByTestId("auth-login-password").or(
      page.locator('input[type="password"]')
    ).first();
    this.submitButton = page.getByTestId("auth-login-submit").or(
      page.getByRole("button", { name: /sign in|register|log in|submit/i })
    ).first();
    this.registerTab = page.getByTestId("auth-register-link").or(
      page.getByRole("tab", { name: /register|sign up/i })
    ).first();
    this.loginTab = page.getByRole("tab", { name: /login|sign in/i });
  }

  async goto() {
    await this.page.goto("/auth");
  }

  async fillLogin(email: string, password: string) {
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
  }

  async fillRegister(email: string, password: string) {
    if (await this.registerTab.isVisible()) {
      await this.registerTab.click();
    }
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
  }

  async submit() {
    await this.submitButton.click();
  }
}
