import { test, expect } from "./fixtures/test-base";
import { setupPageMonitoring, PageMonitoringHandle } from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";

test.describe.serial("M6 Research Synthesis Acceptance Suite", () => {
  let sharedPage: any;
  let monitoring: PageMonitoringHandle;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(120000);
    const context = await browser.newContext({
      viewport: { width: 1280, height: 800 },
    });
    sharedPage = await context.newPage();
    monitoring = setupPageMonitoring(sharedPage);

    // 1. Mock workspace documents to always return 2 valid selectable docs
    await sharedPage.route("**/workspaces/*/documents", async (route: any) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: 1,
              workspace_id: 1,
              document_id: 2,
              added_by: 1,
              added_at: new Date().toISOString(),
              document: {
                id: 2,
                filename: "rag_test_doc_alpha.pdf",
                status: "ready",
                created_at: new Date().toISOString(),
              },
            },
            {
              id: 2,
              workspace_id: 1,
              document_id: 3,
              added_by: 1,
              added_at: new Date().toISOString(),
              document: {
                id: 3,
                filename: "rag_test_doc_beta.pdf",
                status: "ready",
                created_at: new Date().toISOString(),
              },
            },
          ]),
        });
      } else {
        await route.continue();
      }
    });

    // 2. Intercept research runs endpoint
    await sharedPage.route("**/workspaces/*/research/runs", async (route: any) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: 99,
            workspace_id: 1,
            requester_id: 1,
            query: "Compare cross-document findings",
            status: "completed",
            answer: "Synthesis verified across document evidence with cited facts.",
            citations: [
              {
                citation_id: "C1",
                document_id: 2,
                filename: "rag_test_doc_alpha.pdf",
                chunk_id: 101,
                page_number: 1,
                excerpt: "Evidence snippet one verified.",
              },
            ],
            run_metadata: {
              model: "llama3.2",
              provider: "ollama",
              citation_count: 1,
            },
            created_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            error_message: null,
          }),
        });
      } else {
        await route.continue();
      }
    });

    // 3. Authenticate
    await sharedPage.goto("/login");
    await sharedPage.fill("#email", TEST_EMAIL);
    await sharedPage.fill("#password", TEST_PASSWORD);
    await sharedPage.click('button[type="submit"]');
    await sharedPage.waitForLoadState("networkidle");
    await sharedPage.waitForURL(/\/dashboard/, { timeout: 35000 });

    // 4. Select or Create Workspace
    const wsBtn = sharedPage.locator('button[aria-label^="Workspace:"], button[aria-label="Workspaces"]').first();
    await expect(wsBtn).toBeVisible({ timeout: 15000 });
    await wsBtn.click();

    const wsDialog = sharedPage.locator('div[role="dialog"][aria-label="Workspaces"]');
    await expect(wsDialog).toBeVisible({ timeout: 10000 });

    const existingItem = wsDialog.locator("div.max-h-48 button").first();
    if (await existingItem.isVisible({ timeout: 1500 }).catch(() => false)) {
      await existingItem.click();
    } else {
      const createBtn = wsDialog.locator('button:has-text("New workspace")');
      await createBtn.click();
      const input = wsDialog.locator("input#workspace-name-input");
      await input.fill("Neural Research Lab");
      await input.press("Enter");
    }

    // Wait for dialog dismissal
    await expect(wsDialog).not.toBeVisible({ timeout: 5000 });

    // 5. Open research synthesis view from header toggle
    const toggleBtn = sharedPage.locator('[data-testid="toggle-research-synthesis-button"]');
    await expect(toggleBtn).toBeVisible({ timeout: 15000 });
    await toggleBtn.click();

    // 6. Verify research synthesis panel mounted
    await expect(sharedPage.locator('[data-testid="research-synthesis-panel"]')).toBeVisible({ timeout: 15000 });
  });

  test.afterAll(async () => {
    if (sharedPage) {
      await sharedPage.close();
    }
  });

  test("R1 — Run synthesis button is disabled when fewer than 2 documents are selected", async () => {
    const panel = sharedPage.locator('[data-testid="research-synthesis-panel"]');
    const triggerBtn = panel.locator('button:has-text("Run Synthesis")').first();
    await expect(triggerBtn).toBeDisabled();
  });

  test("R2 — Selecting at least 2 documents and entering query enables Run Synthesis button", async () => {
    const panel = sharedPage.locator('[data-testid="research-synthesis-panel"]');
    const checkboxes = panel.locator('input[type="checkbox"]');
    await expect(checkboxes.first()).toBeVisible({ timeout: 10000 });
    const count = await checkboxes.count();
    expect(count).toBeGreaterThanOrEqual(2);

    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();

    const textarea = panel.locator("textarea#synthesis-query");
    await textarea.fill("Compare cross-document findings");

    const triggerBtn = panel.locator('button:has-text("Run Synthesis")').first();
    await expect(triggerBtn).toBeEnabled();
  });

  test("R3 — Synthesis run completes and displays citations & export buttons", async () => {
    const panel = sharedPage.locator('[data-testid="research-synthesis-panel"]');
    const triggerBtn = panel.locator('button:has-text("Run Synthesis")').first();
    await triggerBtn.click();

    const result = sharedPage.locator('[data-testid="research-run-result"]');
    await expect(result).toBeVisible({ timeout: 15000 });
    await expect(result).toContainText("Synthesis verified across document evidence");
    await expect(result.locator('button:has-text("Export Markdown")').first()).toBeVisible();
    await expect(result.locator('button:has-text("Export JSON")').first()).toBeVisible();
  });
});
