import path from "path";
import { test, expect } from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";
const PDF_FIXTURE_PATH = path.resolve(__dirname, "fixtures/rag_test_doc.pdf");

test.describe.serial("M3 Document, RAG & Shell Regression Gate", () => {
  let sharedPage: any;

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext();
    sharedPage = await context.newPage();

    // Single deterministic authentication
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

  test("Test J — existing PDF upload accepts file and completes processing", async () => {
    // 1. Ensure we are in an active chat
    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await expect(newChatBtn).toBeVisible({ timeout: 10000 });
    await newChatBtn.click();

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible({ timeout: 15000 });

    // 2. Open Document Workspace drawer
    const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
    await expect(openDocsBtn).toBeVisible({ timeout: 10000 });
    await openDocsBtn.click();

    // 3. Upload deterministic PDF
    const fileInput = sharedPage.locator('[data-testid="document-upload-file-input"]');
    await fileInput.setInputFiles(PDF_FIXTURE_PATH);

    // 4. Verify document appears in workspace list
    await expect(
      sharedPage.locator('[data-testid="document-list-item"]').or(sharedPage.locator('text=rag_test_doc.pdf')).or(sharedPage.locator('text=Production RAG Specification')).first()
    ).toBeVisible({ timeout: 35000 });

    // 5. Close workspace drawer
    const closeBtn = sharedPage.locator('button[aria-label="Close document workspace"]');
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
    }
  });

  test("Test K — ask question against uploaded document renders response and citation UI", async () => {
    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    
    // Query deterministic factual details from rag_test_doc.pdf
    await promptInput.fill("What database extension is used for retrieval in the specification?");
    await promptInput.press("Enter");

    // Wait for stream completion / assistant message
    const botAvatar = sharedPage.locator("svg.lucide-bot").first();
    await expect(botAvatar).toBeVisible({ timeout: 45000 });

    // Verify citation source badge is rendered
    const citationTrigger = sharedPage.getByRole("button", { name: /source/i }).or(sharedPage.locator('[data-testid="citation-badge"]')).first();
    await expect(citationTrigger).toBeVisible({ timeout: 35000 });
  });

  test("Test L — document isolation holds across distinct chats", async () => {
    // 1. Create fresh Chat B
    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await expect(newChatBtn).toBeVisible({ timeout: 10000 });
    await newChatBtn.click();

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible({ timeout: 15000 });

    // 2. Open document workspace in Chat B
    const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
    await expect(openDocsBtn).toBeVisible({ timeout: 10000 });
    await openDocsBtn.click();

    // 3. Verify Chat B does NOT show Chat A's document
    const isolatedDoc = sharedPage.locator('text=rag_test_doc.pdf');
    await expect(isolatedDoc).toHaveCount(0);

    // Close drawer
    const closeBtn = sharedPage.locator('button[aria-label="Close document workspace"]');
    if (await closeBtn.isVisible()) {
      await closeBtn.click();
    }
  });

  test("Test M — standard chat remains standard chat with AppShell boundaries", async () => {
    // Assert standard layout components remain in place
    await expect(sharedPage.getByRole("navigation").or(sharedPage.locator("aside")).first()).toBeVisible();
    await expect(sharedPage.locator("header")).toBeVisible();
    await expect(sharedPage.getByRole("textbox", { name: /chat prompt/i })).toBeVisible();

    // Assert no workspace split-pane or PDF viewer is mounted
    await expect(sharedPage.locator(".react-pdf__Page, [data-testid='pdf-viewer'], [data-testid='workspace-split-pane']")).toHaveCount(0);
  });
});
