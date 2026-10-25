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
    sharedPage.on("request", (req: any) => {
      if (req.url().includes("doc") || req.url().includes("research")) {
        console.log(">> RESEARCH REQ:", req.method(), req.url());
      }
    });
    sharedPage.on("response", async (res: any) => {
      if (res.url().includes("research")) {
        try {
          const body = await res.json();
          console.log("<< RESEARCH RES:", res.status(), JSON.stringify(body).slice(0, 100));
        } catch {}
      }
    });
    monitoring = setupPageMonitoring(sharedPage);

    // 1. Mock workspace documents: 3 ready docs and 1 processing doc
    await sharedPage.route("**/workspaces/*/documents*", async (route: any) => {
      const url = route.request().url();
      const wsMatch = url.match(/\/workspaces\/(\d+)\/documents/);
      const wsId = wsMatch ? parseInt(wsMatch[1], 10) : 1;

      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: 1,
              workspace_id: wsId,
              document_id: 2,
              filename: "rag_test_doc_alpha.pdf",
              mime_type: "application/pdf",
              status: "ready",
              added_by: 1,
              added_at: new Date().toISOString(),
            },
            {
              id: 2,
              workspace_id: wsId,
              document_id: 3,
              filename: "rag_test_doc_beta.pdf",
              mime_type: "application/pdf",
              status: "ready",
              added_by: 1,
              added_at: new Date().toISOString(),
            },
            {
              id: 3,
              workspace_id: wsId,
              document_id: 4,
              filename: "rag_test_doc_gamma.pdf",
              mime_type: "application/pdf",
              status: "ready",
              added_by: 1,
              added_at: new Date().toISOString(),
            },
            {
              id: 4,
              workspace_id: wsId,
              document_id: 5,
              filename: "rag_test_doc_unready.pdf",
              mime_type: "application/pdf",
              status: "processing",
              added_by: 1,
              added_at: new Date().toISOString(),
            },
          ]),
        });
      } else {
        await route.continue();
      }
    });

    // 2. Mock document metadata and binary file downloads for PDF Viewer
    const minimalPdfBytes = Buffer.from(
      "%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R 6 0 R] /Count 4 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n4 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n5 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n6 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\nxref\n0 7\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000142 00000 n \n0000000192 00000 n \n0000000242 00000 n \n0000000292 00000 n \ntrailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n342\n%%EOF"
    );

    await sharedPage.route(/.*\/documents\/\d+.*$/, async (route: any) => {
      const url = route.request().url();
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }

      if (url.includes("/file")) {
        await route.fulfill({
          status: 200,
          contentType: "application/pdf",
          headers: {
            "Content-Type": "application/pdf",
            "Access-Control-Allow-Origin": "*",
          },
          body: minimalPdfBytes,
        });
        return;
      }

      const docIdMatch = url.match(/\/documents\/(\d+)(?:\/|$|\?)/);
      if (docIdMatch) {
        const docId = parseInt(docIdMatch[1], 10);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: docId,
            chat_id: 1,
            filename: `rag_test_doc_${docId === 2 ? "alpha" : docId === 3 ? "beta" : "gamma"}.pdf`,
            mime_type: "application/pdf",
            status: "ready",
            file_size: 1024 * 1024,
            chunk_count: 12,
            page_count: 4,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            error_message: null,
          }),
        });
        return;
      }

      await route.continue();
    });

    // 3. Mock research runs: dynamically match workspace_id
    await sharedPage.route("**/research/runs*", async (route: any) => {
      const url = route.request().url();
      const wsMatch = url.match(/\/workspaces\/(\d+)\/research\/runs/);
      const wsId = wsMatch ? parseInt(wsMatch[1], 10) : 1;

      const runPayload = {
        id: 888,
        workspace_id: wsId,
        requester_id: 1,
        query: "Compare cross-document findings across Alpha, Beta, and Gamma",
        status: "completed",
        answer: "Cross-document comparative synthesis across 3 papers with verified citations.",
        facets: {
          methodology: "Dual-encoder transformer architecture evaluated across papers [C1].",
          datasets: "Evaluated on SQuAD 2.0 and HotpotQA multi-hop benchmarks [C2].",
          metrics: "Achieved 89.4% F1 and 81.2% EM scores [C1] [C2].",
          findings: "Cross-document synthesis yields higher precision with reranking [C1].",
          limitations: "Increased latency during cross-attention calculation [C2].",
        },
        citations: [
          {
            citation_id: "C1",
            document_id: 2,
            filename: "rag_test_doc_alpha.pdf",
            chunk_id: 101,
            page_number: 1,
            excerpt: "Dual-encoder architecture evaluated on benchmarks.",
          },
          {
            citation_id: "C2",
            document_id: 3,
            filename: "rag_test_doc_beta.pdf",
            chunk_id: 102,
            page_number: 4,
            excerpt: "Evaluated on SQuAD 2.0 and HotpotQA with 89.4% F1.",
          },
        ],
        run_metadata: {
          model: "llama3.2",
          provider: "ollama",
          citation_count: 2,
          selected_document_ids: [2, 3, 4],
        },
        created_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        error_message: null,
      };

      const method = route.request().method();
      if (method === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(runPayload),
        });
      } else if (method === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [runPayload],
            total: 1,
            limit: 20,
            offset: 0,
          }),
        });
      } else {
        await route.continue();
      }
    });

    // 4. Authenticate
    await sharedPage.goto("/login");
    await sharedPage.fill("#email", TEST_EMAIL);
    await sharedPage.fill("#password", TEST_PASSWORD);
    await sharedPage.click('button[type="submit"]');
    await sharedPage.waitForLoadState("networkidle");
    await sharedPage.waitForURL(/\/dashboard/, { timeout: 35000 });

    // 5. Select or Create Workspace
    const wsBtn = sharedPage.locator('button[aria-label^="Workspace:"],button[aria-label="Workspaces"]').first();
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

    // 6. Open research synthesis view from header toggle
    const toggleBtn = sharedPage.locator('[data-testid="toggle-research-synthesis-button"]');
    await expect(toggleBtn).toBeVisible({ timeout: 15000 });
    await toggleBtn.click();

    // 7. Verify research synthesis panel mounted
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

  test("R2 — Selecting 3 ready documents and entering query enables Run Synthesis button", async () => {
    const panel = sharedPage.locator('[data-testid="research-synthesis-panel"]');
    const checkboxes = panel.locator('input[type="checkbox"]');
    await expect(checkboxes.first()).toBeVisible({ timeout: 10000 });
    const count = await checkboxes.count();
    expect(count).toBeGreaterThanOrEqual(3);

    await checkboxes.nth(0).check();
    await checkboxes.nth(1).check();
    await checkboxes.nth(2).check();

    const textarea = panel.locator("textarea#synthesis-query");
    await textarea.fill("Compare cross-document findings across Alpha, Beta, and Gamma");

    const triggerBtn = panel.locator('button:has-text("Run Synthesis")').first();
    await expect(triggerBtn).toBeEnabled();
  });

  test("R3 — Synthesis run completes and displays all 5 structured facets and export buttons", async () => {
    const panel = sharedPage.locator('[data-testid="research-synthesis-panel"]');
    const triggerBtn = panel.locator('button:has-text("Run Synthesis")').first();

    const [response] = await Promise.all([
      sharedPage.waitForResponse((res: any) =>
        res.url().includes("/research/runs") && res.request().method() === "POST"
      ),
      triggerBtn.click(),
    ]);
    expect(response.status()).toBe(200);

    const result = sharedPage.locator('[data-testid="research-run-result"]');
    await expect(result).toBeVisible({ timeout: 15000 });

    // Verify all 5 structured facets render
    const facets = ["methodology", "datasets", "metrics", "findings", "limitations"];
    for (const facet of facets) {
      const card = result.locator(`[data-testid="facet-card-${facet}"]`);
      await expect(card).toBeVisible({ timeout: 10000 });
    }

    // Verify citations list rendered
    const citationAlpha = result.locator('[data-testid="citation-item-C1"]');
    const citationBeta = result.locator('[data-testid="citation-item-C2"]');
    await expect(citationAlpha).toBeVisible({ timeout: 5000 });
    await expect(citationBeta).toBeVisible({ timeout: 5000 });

    await expect(result.locator('button:has-text("Export Markdown")').first()).toBeVisible();
    await expect(result.locator('button:has-text("Export JSON")').first()).toBeVisible();
  });

  test("R4 — Clicking citation navigates to correct document and page in PDF viewer", async () => {
    const result = sharedPage.locator('[data-testid="research-run-result"]');
    const citationBeta = result.locator('[data-testid="citation-item-C2"]');
    await expect(citationBeta).toBeVisible({ timeout: 5000 });

    // Click citation C2 pointing to document 3 (rag_test_doc_beta.pdf) page 4
    await citationBeta.click();
    // 1. Verify URL identifies document 3
    await sharedPage.waitForURL(/docId=3/, { timeout: 10000 });
    expect(sharedPage.url()).toContain("docId=3");

    // 2. Verify PDF viewer resolves and displays
    const pdfViewer = sharedPage.locator('[data-testid="pdf-viewer"]');
    await expect(pdfViewer).toBeVisible({ timeout: 10000 });

    // 3. Verify PDF viewer navigated to page 4
    const pageDisplay = sharedPage.locator('[data-testid="pdf-current-page"]');
    await expect(pageDisplay).toBeVisible({ timeout: 10000 });
    await expect(pageDisplay).toContainText("4");

    // Return to research view for the next test
    await sharedPage.goto("/dashboard?view=research");
    await expect(sharedPage.locator('[data-testid="research-synthesis-panel"]')).toBeVisible({ timeout: 15000 });
  });

  test("R5 — Past runs restore query, selected document IDs, and facet outputs", async () => {
    let panel = sharedPage.locator('[data-testid="research-synthesis-panel"]');

    // Wait for Past Runs button using data-testid and click
    const pastRunsBtn = panel.locator('[data-testid="toggle-history-button"]').or(panel.locator('button:has-text("Past Runs")')).first();
    await expect(pastRunsBtn).toBeVisible({ timeout: 10000 });
    await pastRunsBtn.click();

    const runItem = sharedPage.locator('button:has-text("Compare cross-document findings")').first();
    await expect(runItem).toBeVisible({ timeout: 10000 });
    await runItem.click();

    // 1. Assert query is restored
    const textarea = panel.locator("textarea#synthesis-query");
    await expect(textarea).toHaveValue(/Compare cross-document findings across Alpha, Beta, and Gamma/);

    // 2. Assert selected document IDs (2, 3, 4) are checked
    for (const docId of [2, 3, 4]) {
      const checkbox = panel.locator(`[data-testid="doc-select-checkbox-${docId}"]`);
      await expect(checkbox).toBeChecked();
    }

    // 3. Assert facet output is visible
    let result = sharedPage.locator('[data-testid="research-run-result"]');
    await expect(result).toBeVisible({ timeout: 5000 });
    await expect(result.locator('[data-testid="facet-card-methodology"]')).toBeVisible({ timeout: 5000 });

    // 4. Persistence across reload: reload page and verify run remains available
    await sharedPage.reload();
    panel = sharedPage.locator('[data-testid="research-synthesis-panel"]');
    await expect(panel).toBeVisible({ timeout: 15000 });

    // Active run from history API is reloaded and displayed
    result = sharedPage.locator('[data-testid="research-run-result"]');
    await expect(result).toBeVisible({ timeout: 10000 });
    await expect(result.locator('[data-testid="facet-card-methodology"]')).toBeVisible({ timeout: 5000 });
  });
});
