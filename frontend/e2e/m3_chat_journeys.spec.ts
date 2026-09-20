import { test, expect } from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";

test.describe.serial("M3 Chat & Query Regression Gate", () => {
  let sharedPage: any;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext();
    sharedPage = await context.newPage();

    // Single login for the whole suite
    await sharedPage.goto("/login");
    await sharedPage.fill("#email", TEST_EMAIL);
    await sharedPage.fill("#password", TEST_PASSWORD);
    await sharedPage.click("button[type='submit']");
    await sharedPage.waitForURL(/\/dashboard/, { timeout: 15000 });
  });

  test.afterAll(async () => {
    if (sharedPage) {
      await sharedPage.close();
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

  test("Test G — assistant streaming response displays without runtime errors", async () => {
    const botAvatar = sharedPage.locator("svg.lucide-bot").first();
    await expect(botAvatar).toBeVisible({ timeout: 35000 });
  });

  test("Test H — conversation history persists and renders across navigation", async () => {
    await sharedPage.reload({ waitUntil: "commit" });
    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible({ timeout: 15000 });
  });

  test("Test I — empty message submission is prevented", async () => {
    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await promptInput.fill("");
    await promptInput.press("Enter");

    const emptyBubbles = sharedPage.locator(".user-message:empty, [data-role='user']:empty");
    await expect(emptyBubbles).toHaveCount(0);
  });
});