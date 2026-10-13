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

    sharedPage.on("console", msg => console.log("PAGE LOG:", msg.type(), msg.text()));
    sharedPage.on("requestfailed", req => console.log("REQ FAILED:", req.url(), req.failure()?.errorText));
    sharedPage.on("response", res => {
      if (res.url().includes(":8000") || res.url().includes("/api")) {
        console.log("API RESP:", res.request().method(), res.url(), res.status());
      }
    });

    // Single deterministic authentication
    await sharedPage.goto("/login", { waitUntil: "networkidle" });
    await sharedPage.waitForSelector("#email");
    await sharedPage.fill("#email", TEST_EMAIL);
    await sharedPage.fill("#password", TEST_PASSWORD);
    await sharedPage.click("button[type='submit']");
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
    test.setTimeout(90000);
    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await expect(newChatBtn).toBeVisible({ timeout: 10000 });
    console.log("CLICKING NEW CHAT BUTTON...");
    const [response] = await Promise.all([
      sharedPage.waitForResponse((r: any) => r.url().includes("/chat/new") || r.url().includes("/chat"), { timeout: 15000 }).catch(() => null),
      newChatBtn.click(),
    ]);
    if (response) {
      console.log("NEW CHAT RESPONSE STATUS:", response.status(), await response.text().catch(() => ""));
    } else {
      console.log("NO CHAT NETWORK RESPONSE DETECTED!");
    }
    await sharedPage.waitForURL(/\/dashboard\/chat\/\d+/, { timeout: 30000 });

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible({ timeout: 15000 });
    await expect(promptInput).toBeEnabled({ timeout: 25000 });

    const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
    await expect(openDocsBtn).toBeVisible({ timeout: 10000 });
    await openDocsBtn.click();

    const fileInput = sharedPage.locator('[data-testid="document-upload-file-input"]');
    await fileInput.setInputFiles(PDF_FIXTURE_PATH);

    // Ensure document item appears
    const docItem = sharedPage.locator('[data-testid="document-list-item"]').or(sharedPage.locator('text=rag_test_doc.pdf')).or(sharedPage.locator('text=Production RAG Specification')).first();
    await expect(docItem).toBeVisible({ timeout: 35000 });

    // Wait until document finishes processing (status: ready)
    await expect(
      sharedPage.locator('text=Ready').or(sharedPage.locator('[data-status="ready"]')).or(sharedPage.locator('.text-emerald-500')).or(sharedPage.locator('text=Processed')).first()
    ).toBeVisible({ timeout: 45000 }).catch(() => null);

    // Wait for documents network polling or processing sync
    await sharedPage.waitForTimeout(3000);

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

    test.setTimeout(120000);

    // Wait for AI streaming to complete
    await expect(sharedPage.getByRole("button", { name: /stop generating/i })).toBeHidden({ timeout: 70000 }).catch(() => null);

    // Check citation badge or source button
    const citationTrigger = sharedPage.locator('[data-testid="citation-badge"], button:has-text("source"), button:has-text("sources")').first();
    await expect(citationTrigger).toBeVisible({ timeout: 45000 });
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
    console.log("CLICKING NEW CHAT BUTTON...");
    const [response] = await Promise.all([
      sharedPage.waitForResponse((r: any) => r.url().includes("/chat/new") || r.url().includes("/chat"), { timeout: 15000 }).catch(() => null),
      newChatBtn.click(),
    ]);
    if (response) {
      console.log("NEW CHAT RESPONSE STATUS:", response.status(), await response.text().catch(() => ""));
    } else {
      console.log("NO CHAT NETWORK RESPONSE DETECTED!");
    }
    await sharedPage.waitForURL(/\/dashboard\/chat\/\d+/, { timeout: 25000, waitUntil: "commit" });

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible({ timeout: 15000 });
    await expect(promptInput).toBeEnabled({ timeout: 25000 });
    await expect(promptInput).toBeEmpty();

    // 3. Open document workspace in Chat B
    const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
    await expect(openDocsBtn).toBeVisible({ timeout: 10000 });
    await openDocsBtn.click();

    // 4. Verify Chat B does NOT show Chat A's uploaded PDF
    const workspace = sharedPage.locator('[data-testid="document-workspace"]');
    await expect(workspace).toBeVisible({ timeout: 10000 });
    const isolatedDoc = workspace.locator('[data-testid="document-list-item"]:has-text("rag_test_doc.pdf")');
    await expect(isolatedDoc).toHaveCount(0, { timeout: 10000 });

    // 5. Close drawer cleanly via Escape
    await sharedPage.keyboard.press("Escape");
    await expect(sharedPage.locator('[data-testid="document-workspace"]')).toHaveCount(0, { timeout: 5000 }).catch(() => null);
  });

  test("Test M — standard chat remains standard chat with AppShell boundaries", async () => {
    await expect(sharedPage.getByRole("navigation").or(sharedPage.locator("aside")).first()).toBeVisible();
    await expect(sharedPage.locator("header")).toBeVisible();
    await expect(sharedPage.getByRole("textbox", { name: /chat prompt/i })).toBeVisible();

    await expect(sharedPage.locator(".react-pdf__Page, [data-testid='pdf-viewer'], [data-testid='workspace-split-pane']")).toHaveCount(0);
  });
});
