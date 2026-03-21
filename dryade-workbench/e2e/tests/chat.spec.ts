import { test, expect } from "../fixtures/mock-auth";
import { ChatPage } from "../page-objects/ChatPage";

test.describe("Chat Page", () => {
  test("should load chat page with input area", async ({ authedPage }) => {
    const chat = new ChatPage(authedPage);
    await chat.goto();
    await expect(chat.messageInput).toBeVisible({ timeout: 10_000 });
  });

  test("should display mode selector", async ({ authedPage }) => {
    const chat = new ChatPage(authedPage);
    await chat.goto();
    // Mode selector shows chat/planner/orchestrate options
    const modeSelector = authedPage.locator(
      "button:has-text('chat'), button:has-text('planner'), button:has-text('orchestrate'), " +
      "[data-testid='mode-selector'], select, [role='combobox']"
    ).first();
    await expect(modeSelector).toBeVisible({ timeout: 10_000 });
  });

  test("should type a message in the input", async ({ authedPage }) => {
    const chat = new ChatPage(authedPage);
    await chat.goto();
    await chat.messageInput.fill("Hello, test message");
    const value = await chat.messageInput.inputValue();
    expect(value).toBe("Hello, test message");
  });

  test("should have send button", async ({ authedPage }) => {
    const chat = new ChatPage(authedPage);
    await chat.goto();
    await chat.messageInput.fill("test");
    await expect(chat.sendButton).toBeVisible({ timeout: 5_000 });
  });

  test("should show empty state or conversation content", async ({ authedPage }) => {
    const chat = new ChatPage(authedPage);
    await chat.goto();
    // Wait for React to render — either message input or empty state should appear
    const inputOrEmpty = chat.messageInput.or(
      authedPage.locator("[data-testid='empty-state'], .empty-state, :text('Start a conversation'), :text('How can I help')")
    );
    await expect(inputOrEmpty.first()).toBeVisible({ timeout: 10_000 });
  });

  test("should navigate between chat routes", async ({ authedPage }) => {
    await authedPage.goto("/workspace/chat");
    await authedPage.waitForLoadState("domcontentloaded");
    await expect(authedPage).toHaveURL(/\/workspace\/chat/);
    // Navigate to non-existent conversation — should not crash
    await authedPage.goto("/workspace/chat/nonexistent-id");
    await authedPage.waitForLoadState("domcontentloaded");
    await expect(authedPage).toHaveURL(/\/workspace\/chat/);
  });
});
