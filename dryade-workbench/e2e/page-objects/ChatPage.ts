import type { Page, Locator } from "@playwright/test";

/**
 * Selector for assistant messages in chat.
 * MessageItem.tsx now has data-testid="chat-assistant-message" (added phase 216-03).
 * Fallback: .prose wrapper inside the message bubble.
 */
const ASSISTANT_MSG_SELECTOR = "[data-testid='chat-assistant-message'], .prose";

const USER_MSG_SELECTOR =
  "[data-testid='chat-user-message'], [class*='border-r-2'][class*='border-primary'], [class*='ml-auto']";

export class ChatPage {
  readonly page: Page;
  readonly messageInput: Locator;
  readonly sendButton: Locator;

  constructor(page: Page) {
    this.page = page;
    // Prefer data-testid selectors (added phase 216-03), fallback to fragile selectors
    this.messageInput = page.getByTestId("chat-message-input").or(
      page.locator("textarea, input[placeholder*='message' i], input[placeholder*='type' i], [contenteditable='true']")
    ).first();
    this.sendButton = page.getByTestId("chat-send-button").or(
      page.locator("button[type='submit'], button:has-text('Send'), button[aria-label*='send' i]")
    ).first();
  }

  async goto(conversationId?: string) {
    const path = conversationId
      ? `/workspace/chat/${conversationId}`
      : "/workspace/chat";
    await this.page.goto(path);
    // Use domcontentloaded instead of networkidle — SSE/WebSocket connections
    // can keep networkidle from resolving
    await this.page.waitForLoadState("domcontentloaded");
    // Wait for the chat input to appear (React hydration + data loading)
    await this.messageInput.waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});
  }

  async sendMessage(text: string) {
    // Remove any toast notifications that might intercept button clicks (Sonner toasts)
    await this.page.evaluate(() => {
      document.querySelectorAll("[data-sonner-toast]").forEach(el => el.remove());
    });
    await this.messageInput.fill(text);
    await this.sendButton.click({ timeout: 10_000 });
  }

  async waitForResponse(timeout = 10_000) {
    await this.page
      .locator(ASSISTANT_MSG_SELECTOR)
      .first()
      .waitFor({ timeout });
  }

  getAssistantMessages() {
    return this.page.locator(ASSISTANT_MSG_SELECTOR);
  }

  getUserMessages() {
    return this.page.locator(USER_MSG_SELECTOR);
  }

  async getConversationList() {
    // UnifiedSidebar wraps each conversation in DraggableConversationItem (.cursor-grab)
    // Wait for conversation items to load
    await this.page.locator('.cursor-grab').first().waitFor({ timeout: 5_000 }).catch(() => {});
    const items = await this.page.locator('.cursor-grab').all();
    if (items.length > 0) return items;
    // Fallback: conversation items in ConversationsPanel or ConversationList (button[role=option])
    return this.page
      .locator("button[role='option'], [data-testid='conversation-item']")
      .all();
  }

  async getEmptyState() {
    return this.page.locator("[data-testid='empty-state'], .empty-state, :text('Start a conversation'), :text('How can I help')").first();
  }
}
