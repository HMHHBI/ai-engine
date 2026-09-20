import path from "path";
import { test, expect, attachPageMonitoring, PageMonitoringHandle } from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";
const PDF_FIXTURE_PATH = path.resolve(__dirname, "fixtures/rag_test_doc.pdf");

test.describe.serial("M3 Document, RAG & Shell Regression Gate", () => {
  let sharedPage: any;
  let monitoring: PageMonitoringHandle;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(60000);
    const context = await browser.newContext();
    sharedPage = await context.newPage();
    monitoring = attachPageMonitoring(sharedPage);

    // Single deterministic authentication
    await sharedPage.goto("/login");
    await sharedPage.fill("#email", TEST_EMAIL);
    await sharedPage.fill("#password", TEST_PASSWORD);
    await sharedPage.click("button[type='submit']");
    await sharedPage.waitForLoadState("networkidle");
    await sharedPage.waitForURL(/\/dashboard/, { timeout: 30000 });
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

  test("Test J — existing PDF upload accepts file and completes processing", async () => {
    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await expect(newChatBtn).toBeVisible({ timeout: 10000 });
    await newChatBtn.click();

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible({ timeout: 15000 });

    const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
    await expect(openDocsBtn).toBeVisible({ timeout: 10000 });
    await openDocsBtn.click();

    const fileInput = sharedPage.locator('[data-testid="document-upload-file-input"]');
    await fileInput.setInputFiles(PDF_FIXTURE_PATH);

    await expect(
      sharedPage.locator('[data-testid="document-list-item"]').or(sharedPage.locator('text=rag_test_doc.pdf')).or(sharedPage.locator('text=Production RAG Specification')).first()
    ).toBeVisible({ timeout: 35000 });

    // Close drawer via close button or Escape
    const closeBtn = sharedPage.locator('button[aria-label="Close document workspace"]');
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
    } else {
      await sharedPage.keyboard.press("Escape");
    }
    await sharedPage.waitForTimeout(500);
  });

  test("Test K — ask question against uploaded document renders response and citation UI", async () => {
    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeEnabled({ timeout: 15000 });
    
    await promptInput.fill("What database extension is used for retrieval in the specification?");
    await promptInput.press("Enter");

    const botAvatar = sharedPage.locator("svg.lucide-bot").first();
    await expect(botAvatar).toBeVisible({ timeout: 45000 });

    const citationTrigger = sharedPage.getByRole("button", { name: /source/i }).or(sharedPage.locator('[data-testid="citation-badge"]')).first();
    await expect(citationTrigger).toBeVisible({ timeout: 35000 });
  });

  test("Test L — document isolation holds across distinct chats", async () => {
    // 1. Ensure any lingering drawer is closed before switching chats
    const lingeringClose = sharedPage.locator('button[aria-label="Close document workspace"]');
    if (await lingeringClose.isVisible()) {
      await lingeringClose.click();
      await sharedPage.waitForTimeout(300);
    }

    // 2. Create fresh Chat B
    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await expect(newChatBtn).toBeVisible({ timeout: 10000 });
    await newChatBtn.click();

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible({ timeout: 15000 });
    await expect(promptInput).toBeEmpty();

    // 3. Open document workspace in Chat B
    const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
    await expect(openDocsBtn).toBeVisible({ timeout: 10000 });
    await openDocsBtn.click();

    // 4. Verify Chat B does NOT show Chat A's uploaded PDF
    const isolatedDoc = sharedPage.locator('[data-testid="document-list-item"]:has-text("rag_test_doc.pdf"), div:has-text("rag_test_doc.pdf")').filter({ hasNot: sharedPage.locator("nav") });
    await expect(isolatedDoc).toHaveCount(0, { timeout: 10000 });

    // 5. Close drawer cleanly
    const closeBtn = sharedPage.locator('button[aria-label="Close document workspace"]');
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
    } else {
      await sharedPage.keyboard.press("Escape");
    }
  });

  test("Test M — standard chat remains standard chat with AppShell boundaries", async () => {
    await expect(sharedPage.getByRole("navigation").or(sharedPage.locator("aside")).first()).toBeVisible();
    await expect(sharedPage.locator("header")).toBeVisible();
    await expect(sharedPage.getByRole("textbox", { name: /chat prompt/i })).toBeVisible();

    await expect(sharedPage.locator(".react-pdf__Page, [data-testid='pdf-viewer'], [data-testid='workspace-split-pane']")).toHaveCount(0);
  });
});
