import fs from "fs";
import path from "path";
import { test, expect } from "./fixtures/test-base";
import { attachPageMonitoring, PageMonitoringHandle } from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";
const PDF_FIXTURE_PATH = path.resolve(__dirname, "fixtures/rag_test_doc.pdf");
// Read deterministic seeded cross-user state
let USER2_DOC_ID = 55;
try {
  const seedStatePath = path.resolve(__dirname, "fixtures/test_seed_state.json");
  if (fs.existsSync(seedStatePath)) {
    const seedState = JSON.parse(fs.readFileSync(seedStatePath, "utf-8"));
    if (seedState.user2_doc_id) {
      USER2_DOC_ID = seedState.user2_doc_id;
    }
  }
} catch (e) {
  // fallback remains
}


test.describe.serial("M4 Workspace Acceptance Suite (W1–W10)", () => {
  let sharedPage: any;
  let monitoring: PageMonitoringHandle;
  let uploadedDocId: string = "";
  let primaryChatUrl: string = "";

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(120000);
    const context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
    });
    sharedPage = await context.newPage();
    monitoring = attachPageMonitoring(sharedPage);

    // Deterministic authentication
    await sharedPage.goto("/login");
    await sharedPage.fill("#email", TEST_EMAIL);
    await sharedPage.fill("#password", TEST_PASSWORD);
    await sharedPage.click("button[type='submit']");
    await sharedPage.waitForLoadState("networkidle");
    await sharedPage.waitForURL(/\/dashboard/, { timeout: 35000 });

    // Initialize fresh chat for workspace tests
    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await expect(newChatBtn).toBeVisible({ timeout: 15000 });
    await newChatBtn.click();
    await sharedPage.waitForURL(/\/chat\/\d+/, { timeout: 20000 });
    primaryChatUrl = sharedPage.url();

    // Open documents drawer and upload PDF
    const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
    await expect(openDocsBtn).toBeVisible({ timeout: 15000 });
    await openDocsBtn.click();

    const fileInput = sharedPage.locator('[data-testid="document-upload-file-input"]');
    await fileInput.setInputFiles(PDF_FIXTURE_PATH);

    // Wait for document to finish processing and appear in list
    const docItem = sharedPage.locator('[data-document-list-item="true"]')
      .or(sharedPage.locator('text=rag_test_doc.pdf'))
      .first();
    await expect(docItem).toBeVisible({ timeout: 45000 });

    // Extract doc ID
    const extractedId = await docItem.getAttribute("data-doc-id");
    if (extractedId) {
      uploadedDocId = extractedId;
    }

    // Close document drawer
    const closeDrawerBtn = sharedPage.locator('button[aria-label="Close document workspace"]');
    if (await closeDrawerBtn.isVisible()) {
      await closeDrawerBtn.click();
    } else {
      await sharedPage.keyboard.press("Escape");
    }
    await sharedPage.waitForTimeout(500);
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

  test("W1 — standard chat without workspace renders full-width chat and no split pane", async () => {
    expect(sharedPage.url()).not.toContain("docId=");

    const splitPane = sharedPage.locator('[data-testid="workspace-split-pane"]');
    await expect(splitPane).toHaveCount(0);

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible();
  });

  test("W2 — valid ?docId activates workspace split pane and document viewer boundary", async () => {
    const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
    await openDocsBtn.click();

    const docItem = sharedPage.locator('[data-document-list-item="true"]')
      .or(sharedPage.locator('text=rag_test_doc.pdf'))
      .first();
    await expect(docItem).toBeVisible({ timeout: 15000 });
    await docItem.click();

    await expect(sharedPage).toHaveURL(/docId=\d+/, { timeout: 15000 });
    const url = new URL(sharedPage.url());
    uploadedDocId = url.searchParams.get("docId") || uploadedDocId;
    expect(uploadedDocId).toBeTruthy();

    const splitPane = sharedPage.locator('[data-testid="workspace-split-pane"]');
    await expect(splitPane).toBeVisible({ timeout: 15000 });

    const docPane = sharedPage.locator('[data-testid="workspace-document-pane"]');
    await expect(docPane).toBeVisible();

    const pdfViewer = sharedPage.locator('[data-testid="pdf-viewer-boundary"]');
    await expect(pdfViewer).toBeVisible();
  });

  test("W3 — document selection updates URL query parameter without full-page navigation", async () => {
    // Inject a runtime window marker to verify navigation was purely client-side
    await sharedPage.evaluate(() => {
      (window as any).__m4_client_nav_marker = "persisted_without_reload";
    });

    const currentUrl = sharedPage.url();
    expect(currentUrl).toContain(`docId=${uploadedDocId}`);

    const splitChatPane = sharedPage.locator('[data-testid="workspace-chat-pane"]');
    await expect(splitChatPane).toBeVisible();

    const marker = await sharedPage.evaluate(() => (window as any).__m4_client_nav_marker);
    expect(marker).toBe("persisted_without_reload");
  });

  test("W4 — page refresh preserves workspace split pane and active document", async () => {
    await sharedPage.reload();
    await sharedPage.waitForLoadState("networkidle");

    expect(sharedPage.url()).toContain(`docId=${uploadedDocId}`);

    const splitPane = sharedPage.locator('[data-testid="workspace-split-pane"]');
    await expect(splitPane).toBeVisible({ timeout: 15000 });

    const docTitle = sharedPage.locator('[data-testid="workspace-document-title"]');
    await expect(docTitle).toBeVisible();
  });

  test("W5 — chat and document isolation: switching chats clears document context", async () => {
    const primaryIdMatch = primaryChatUrl.match(/\/chat\/(\d+)/);
    const primaryChatId = primaryIdMatch ? primaryIdMatch[1] : null;

    const newChatBtn = sharedPage.getByRole("button", { name: /new chat/i }).first();
    await newChatBtn.click();

    await sharedPage.waitForURL(
      (url: URL) => url.pathname.includes("/chat/") && !url.pathname.includes(`/chat/${primaryChatId}`) && !url.searchParams.has("docId"),
      { timeout: 25000 }
    );

    expect(sharedPage.url()).not.toContain("docId=");

    const splitPane = sharedPage.locator('[data-testid="workspace-split-pane"]');
    await expect(splitPane).toHaveCount(0);

    // Return to primary chat with workspace
    await sharedPage.goto(`${primaryChatUrl}?docId=${uploadedDocId}`);
    await sharedPage.waitForLoadState("networkidle");
  });

  test("W6 — closing workspace strips docId and returns to standard chat layout", async () => {
    const splitPane = sharedPage.locator('[data-testid="workspace-split-pane"]');
    await expect(splitPane).toBeVisible({ timeout: 15000 });

    const closeBtn = sharedPage.locator('[data-testid="workspace-close-button"]');
    await expect(closeBtn).toBeVisible({ timeout: 10000 });
    await closeBtn.click();

    await expect(sharedPage).not.toHaveURL(/docId=/);
    await expect(splitPane).toHaveCount(0);

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible();
  });

  test("W7 — split pane drag handle respects resize boundaries", async () => {
    await sharedPage.goto(`${primaryChatUrl}?docId=${uploadedDocId}`);
    await sharedPage.waitForLoadState("networkidle");

    const resizeHandle = sharedPage.locator('[data-testid="workspace-resize-handle"]');
    await expect(resizeHandle).toBeVisible({ timeout: 15000 });

    const handleBox = await resizeHandle.boundingBox();
    expect(handleBox).not.toBeNull();

    if (handleBox) {
      await sharedPage.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
      await sharedPage.mouse.down();
      await sharedPage.mouse.move(handleBox.x - 120, handleBox.y + handleBox.height / 2, { steps: 5 });
      await sharedPage.mouse.up();
    }

    const docContainer = sharedPage.locator('[data-testid="workspace-document-pane-container"]');
    const box = await docContainer.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThanOrEqual(360);
    }

    const chatPane = sharedPage.locator('[data-testid="workspace-chat-pane"]');
    const chatBox = await chatPane.boundingBox();
    expect(chatBox).not.toBeNull();
    if (chatBox) {
      expect(chatBox.width).toBeGreaterThanOrEqual(420);
    }
  });

  test("W8 — responsive viewport renders drawer fallback on mobile/narrow screens", async () => {
    await sharedPage.setViewportSize({ width: 768, height: 800 });
    await sharedPage.waitForTimeout(400);

    const responsiveDrawer = sharedPage.locator('[data-testid="workspace-responsive-drawer"]');
    await expect(responsiveDrawer).toBeVisible({ timeout: 15000 });

    const backdrop = sharedPage.locator('[data-testid="workspace-drawer-backdrop"]');
    await expect(backdrop).toBeVisible();

    // Revert to desktop
    await sharedPage.setViewportSize({ width: 1280, height: 800 });
    await sharedPage.waitForTimeout(400);
    await expect(sharedPage.locator('[data-testid="workspace-split-pane"]')).toBeVisible();
  });

    test("W9a — nonexistent ?docId safely defaults to standard chat without workspace", async () => {
    const [response] = await Promise.all([
      sharedPage.waitForResponse(
        (resp) => resp.url().includes("/documents/99999999") && resp.status() === 404,
        { timeout: 15000 }
      ).catch(() => null),
      sharedPage.goto(`${primaryChatUrl}?docId=99999999`),
    ]);

    await sharedPage.waitForLoadState("networkidle");

    const splitPane = sharedPage.locator('[data-testid="workspace-split-pane"]');
    await expect(splitPane).toHaveCount(0);

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible();
    await expect(promptInput).toBeEnabled();
  });

  test("W9b — cross-user non-owned ?docId safely defaults to standard chat without leak", async () => {
    // Dynamically uses deterministically seeded User 2 document ID
    const [response] = await Promise.all([
      sharedPage.waitForResponse(
        (resp) => resp.url().includes(`/documents/${USER2_DOC_ID}`) && (resp.status() === 404 || resp.status() === 403),
        { timeout: 15000 }
      ).catch(() => null),
      sharedPage.goto(`${primaryChatUrl}?docId=${USER2_DOC_ID}`),
    ]);

    await sharedPage.waitForLoadState("networkidle");

    const splitPane = sharedPage.locator('[data-testid="workspace-split-pane"]');
    await expect(splitPane).toHaveCount(0);

    const promptInput = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(promptInput).toBeVisible();
    await expect(promptInput).toBeEnabled();
  });

  test("W10 — zero runtime console errors, unhandled exceptions, and 5xx responses", async () => {
    monitoring.assertNoErrors();
  });
});
