import { test, expect, attachPageMonitoring, PageMonitoringHandle } from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";

test.describe.serial("M3 Chat & Query Regression Gate", () => {
  let sharedPage: any;
  let monitoring: PageMonitoringHandle;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(60000);
    const context = await browser.newContext();
    sharedPage = await context.newPage();
    monitoring = attachPageMonitoring(sharedPage);

    await sharedPage.goto("/login");
    await sharedPage.fill("#email", TEST_EMAIL);
    await sharedPage.fill("#password", TEST_PASSWORD);
    await sharedPage.click("button[type='submit']");
    await sharedPage.waitForLoadState("networkidle");
    await sharedPage.waitForURL(/\/dashboard/, { timeout: 20000 });
  });

  test.afterAll(async () => {
    try {
      if (monitoring) {
        monitoring.assertNoErrors();
      }
    } finally {
      if (sharedPage) {
        await sharedPage.close();
      }
    }
  });

  test("Test E — new chat creation initializes fresh thread state", async () => {
    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await expect(newChatBtn).toBeVisible({ timeout: 10000 });
    await newChatBtn.click();

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible({ timeout: 15000 });
    await expect(promptInput).toBeEnabled({ timeout: 15000 });
    await expect(promptInput).toBeEmpty();
  });

  test("Test F — message send renders user bubble immediately", async () => {
    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    const testPrompt = `M3_Msg_${Date.now()}`;

    await promptInput.fill(testPrompt);
    await promptInput.press("Enter");

    await expect(sharedPage.locator("div.whitespace-pre-wrap", { hasText: testPrompt })).toBeVisible({ timeout: 10000 });
  });

  test("Test G — assistant streaming response completes and composer remains usable", async () => {
    const botAvatar = sharedPage.locator("svg.lucide-bot").first();
    await expect(botAvatar).toBeVisible({ timeout: 45000 });

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeEnabled({ timeout: 45000 });

    const messageContainers = sharedPage.locator(".prose, div.whitespace-pre-wrap, [data-role='assistant']");
    await expect(messageContainers.last()).toBeVisible({ timeout: 10000 });
    const text = await messageContainers.last().innerText();
    expect(text.trim().length).toBeGreaterThan(0);
  });

  test("Test H — multi-chat navigation isolates messages across threads", async () => {
    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });

    // Step 1: Send unique message in Chat A
    const msgChatA = `Chat_A_${Date.now()}`;
    await promptInput.fill(msgChatA);
    await promptInput.press("Enter");
    await expect(sharedPage.locator("div.whitespace-pre-wrap", { hasText: msgChatA })).toBeVisible({ timeout: 15000 });
    await expect(promptInput).toBeEnabled({ timeout: 45000 });

    // Step 2: Create Chat B
    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await expect(newChatBtn).toBeVisible({ timeout: 10000 });
    await newChatBtn.click();
    await expect(promptInput).toBeEmpty({ timeout: 15000 });
    await expect(promptInput).toBeEnabled({ timeout: 15000 });

    // Step 3: Send unique message in Chat B
    const msgChatB = `Chat_B_${Date.now()}`;
    await promptInput.fill(msgChatB);
    await promptInput.press("Enter");
    await expect(sharedPage.locator("div.whitespace-pre-wrap", { hasText: msgChatB })).toBeVisible({ timeout: 15000 });
    await expect(promptInput).toBeEnabled({ timeout: 45000 });

    // Step 4: Verify Chat B does NOT display Chat A's message
    await expect(sharedPage.locator("div.whitespace-pre-wrap", { hasText: msgChatA })).toHaveCount(0);

    // Step 5: Navigate back to Chat A via sidebar
    const sidebarHistoryItems = sharedPage.locator('nav[aria-label="Chat history"] button:has(svg.lucide-message-square)');
    await expect(sidebarHistoryItems.first()).toBeVisible({ timeout: 10000 });
    
    const count = await sidebarHistoryItems.count();
    if (count > 1) {
      // Click the previous conversation (Chat A)
      await sidebarHistoryItems.nth(1).click();
      
      // Wait for Chat B's message to disappear and Chat A's message to become visible
      await expect(sharedPage.locator("div.whitespace-pre-wrap", { hasText: msgChatB })).toBeHidden({ timeout: 15000 });
      await expect(sharedPage.locator("div.whitespace-pre-wrap", { hasText: msgChatA })).toBeVisible({ timeout: 15000 });
    }
  });

  test("Test I — empty message submission is prevented", async () => {
    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeEnabled({ timeout: 15000 });
    await promptInput.fill("");
    await promptInput.press("Enter");

    const emptyBubbles = sharedPage.locator(".user-message:empty, [data-role='user']:empty");
    await expect(emptyBubbles).toHaveCount(0);
  });
});
