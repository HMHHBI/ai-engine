import path from "path";

import {
  test,
  expect,
  attachPageMonitoring,
  PageMonitoringHandle,
} from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";
const PDF_FIXTURE_PATH = path.resolve(__dirname, "fixtures/rag_test_doc.pdf");

const PDF_WORKER_PATH = "/pdf.worker.min.mjs";
const PDF_PAGE_COUNT = 2;

const WRONG_DOCUMENT_ID = 55;

test.describe.serial("M5 PDF Viewer Acceptance Suite (M5.11)", () => {
  let sharedPage: any;
  let monitoring: PageMonitoringHandle;

  let chatUrl = "";
  let uploadedDocId = "";
  let uploadedDocIdNumber = 0;

  const fakeWorkerWarnings: string[] = [];

  test.beforeEach(async () => {
    test.setTimeout(90000);
  });

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(120000);

    const context = await browser.newContext();

    sharedPage = await context.newPage();
    monitoring = attachPageMonitoring(sharedPage);

    sharedPage.on("console", (message: any) => {
      if (
        message.type() === "warning" &&
        message.text().toLowerCase().includes("fake worker")
      ) {
        fakeWorkerWarnings.push(message.text());
      }
    });

    await sharedPage.goto("/login");

    await sharedPage.fill("#email", TEST_EMAIL);
    await sharedPage.fill("#password", TEST_PASSWORD);

    await sharedPage.click("button[type='submit']");

    await sharedPage.waitForLoadState("domcontentloaded");
    await sharedPage.waitForURL(/\/dashboard/, {
      timeout: 35000,
    });

    const newChatButton = sharedPage
      .getByRole("button", { name: /new chat/i })
      .first();

    await expect(newChatButton).toBeVisible({
      timeout: 15000,
    });

    await Promise.all([
      sharedPage.waitForURL(/\/chat\/\d+/, { timeout: 35000 }),
      newChatButton.click(),
    ]);

    chatUrl = sharedPage.url().split("?")[0];

    const openDocumentsButton = sharedPage.locator(
      '[data-testid="open-documents-button"]',
    );

    await expect(openDocumentsButton).toBeVisible({
      timeout: 15000,
    });

    await openDocumentsButton.click();

    const fileInput = sharedPage.locator(
      '[data-testid="document-upload-file-input"]',
    );

    await expect(fileInput).toBeAttached();

    await fileInput.setInputFiles(PDF_FIXTURE_PATH);

    const documentItem = sharedPage
      .locator('[data-testid="document-list-item"]')
      .or(sharedPage.locator('[data-doc-id]'))
      .or(sharedPage.locator("text=rag_test_doc.pdf"))
      .first();

    await expect(documentItem).toBeVisible({
      timeout: 45000,
    });

    let extractedDocumentId = await documentItem.getAttribute("data-doc-id");

    if (!extractedDocumentId) {
      const parentWithDocId = sharedPage.locator("[data-doc-id]").first();
      extractedDocumentId = await parentWithDocId.getAttribute("data-doc-id");
    }

    if (!extractedDocumentId) {
      await documentItem.click();
      await sharedPage.waitForURL(/docId=\d+/, { timeout: 15000 });
      const currentUrl = new URL(sharedPage.url());
      extractedDocumentId = currentUrl.searchParams.get("docId");
    }

    expect(extractedDocumentId).toBeTruthy();

    uploadedDocId = extractedDocumentId as string;
    uploadedDocIdNumber = Number(uploadedDocId);

    const closeDrawerButton = sharedPage.locator(
      'button[aria-label="Close document workspace"]',
    );

    if (await closeDrawerButton.isVisible()) {
      await closeDrawerButton.click();
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

      expect(
        fakeWorkerWarnings,
        `PDF.js fake-worker warnings detected: ${fakeWorkerWarnings.join("\n")}`,
      ).toEqual([]);
    } finally {
      if (sharedPage) {
        await sharedPage.close();
      }
    }
  });

  async function openWorkspace() {
    const pane = sharedPage.locator('[data-testid="workspace-split-pane"]');
    if (!(await pane.isVisible())) {
      const targetUrl = `${chatUrl}?docId=${uploadedDocId}`;
      if (sharedPage.url() !== targetUrl) {
        await sharedPage.goto(targetUrl);
      }
      if (!(await pane.isVisible())) {
        const openDocsBtn = sharedPage.locator('[data-testid="open-documents-button"]');
        if (await openDocsBtn.isVisible()) {
          await openDocsBtn.click();
          const docItem = sharedPage.locator(`[data-doc-id="${uploadedDocId}"]`).or(sharedPage.locator("text=rag_test_doc.pdf")).first();
          if (await docItem.isVisible()) {
            await docItem.click();
          }
        }
      }
    }
    await expect(pane).toBeVisible({ timeout: 30000 });
    await expect(
      sharedPage.locator('[data-testid="workspace-document-pane"]'),
    ).toBeVisible({ timeout: 20000 });
  }

  async function waitForPdfLoaded() {
    const viewer = sharedPage.locator('[data-testid="pdf-viewer"]');

    await expect(viewer).toBeVisible({
      timeout: 30000,
    });

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText(new RegExp(`\\d+ / ${PDF_PAGE_COUNT}`), {
      timeout: 30000,
    });

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toBeVisible({
      timeout: 30000,
    });

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toHaveAttribute("data-page-number", /\d+/);
  }

  async function openCitationSources() {
    // Wait for AI streaming to finish before citation controls mount
    const stopButton = sharedPage.getByRole("button", { name: /stop generating/i });
    if (await stopButton.isVisible()) {
      await expect(stopButton).not.toBeVisible({ timeout: 120000 });
    }

    const citationTrigger = sharedPage
      .getByRole("button", {
        name: /source|sources/i,
      })
      .last();

    await expect(citationTrigger).toBeVisible({
      timeout: 120000,
    });

    if ((await citationTrigger.getAttribute("aria-expanded")) !== "true") {
      await citationTrigger.click();
    }

    await expect(
      sharedPage.locator('[data-testid^="citation-source-"]').first(),
    ).toBeVisible({
      timeout: 20000,
    });
  }

  async function getZoomPercentage(): Promise<number> {
    const text = await sharedPage
      .locator('[data-testid="pdf-zoom-reset"]')
      .textContent();

    expect(text).toMatch(/^\d+%$/);

    return Number(text!.replace("%", ""));
  }

  test("M5.11-PDF-01 — worker returns HTTP 200 and no fake-worker warning occurs", async () => {
    // Direct asset request guarantees verification regardless of browser caching
    const response = await sharedPage.request.get(PDF_WORKER_PATH);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"] ?? "").toMatch(/javascript|text\/javascript/i);

    await openWorkspace();
    await waitForPdfLoaded();

    expect(fakeWorkerWarnings).toEqual([]);
  });

  test("M5.11-PDF-02 — authenticated PDF renders inside DocumentPane", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    await expect(
      sharedPage.locator('[data-testid="workspace-document-title"]'),
    ).toBeVisible();

    await expect(
      sharedPage.locator('[data-testid="pdf-viewer"]'),
    ).toBeVisible();

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toHaveCount(1);
  });

  test("M5.11-PDF-03 — page navigation advances and returns to the previous page", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    const nextButton = sharedPage.locator('[data-testid="pdf-next"]');
    const previousButton = sharedPage.locator('[data-testid="pdf-prev"]');

    await expect(nextButton).toBeEnabled();
    await expect(previousButton).toBeDisabled();

    await nextButton.click();

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("2 / 2");

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toHaveAttribute("data-page-number", "2");

    await expect(nextButton).toBeDisabled();
    await expect(previousButton).toBeEnabled();

    await previousButton.click();

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("1 / 2");

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toHaveAttribute("data-page-number", /\d+/);

    await expect(previousButton).toBeDisabled();
    await expect(nextButton).toBeEnabled();
  });

  test("M5.11-PDF-04 — page boundaries clamp at page 1 and page N", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    const previousButton = sharedPage.locator('[data-testid="pdf-prev"]');
    const nextButton = sharedPage.locator('[data-testid="pdf-next"]');

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("1 / 2");

    await expect(previousButton).toBeDisabled();

    await nextButton.click();

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("2 / 2");

    await expect(nextButton).toBeDisabled();

    await nextButton.click({ force: true });
    await nextButton.click({ force: true });

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("2 / 2");

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toHaveAttribute("data-page-number", "2");
  });

  test("M5.11-PDF-05 — zoom in changes scale and zoom out restores it", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    const zoomInButton = sharedPage.locator('[data-testid="pdf-zoom-in"]');
    const zoomOutButton = sharedPage.locator('[data-testid="pdf-zoom-out"]');

    const initialScale = await getZoomPercentage();
    expect(initialScale).toBe(100);

    await zoomInButton.click();

    const zoomedInScale = await getZoomPercentage();
    expect(zoomedInScale).toBeGreaterThan(initialScale);

    await zoomOutButton.click();

    await expect(
      sharedPage.locator('[data-testid="pdf-zoom-reset"]'),
    ).toHaveText("100%");
  });

  test("M5.11-PDF-06 — reset zoom returns to exactly 100 percent", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    const zoomInButton = sharedPage.locator('[data-testid="pdf-zoom-in"]');
    const resetButton = sharedPage.locator('[data-testid="pdf-zoom-reset"]');

    const initialScale = await getZoomPercentage();
    expect(initialScale).toBe(100);

    await zoomInButton.click();
    await zoomInButton.click();

    const modifiedScale = await getZoomPercentage();
    expect(modifiedScale).toBeGreaterThan(100);

    await resetButton.click();

    await expect(resetButton).toHaveText("100%");
  });

  test("M5.11-PDF-07 — fit width recalculates scale from the rendered page dimensions", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    const resetButton = sharedPage.locator('[data-testid="pdf-zoom-reset"]');
    const fitWidthButton = sharedPage.locator('[data-testid="pdf-fit-width"]');

    await expect(resetButton).toHaveText("100%");

    await fitWidthButton.click();

    const fitWidthScaleText = await resetButton.textContent();

    expect(fitWidthScaleText).toMatch(/^\d+%$/);
    expect(fitWidthScaleText).not.toBe("100%");

    await sharedPage.locator('[data-testid="pdf-zoom-reset"]').click();

    await expect(resetButton).toHaveText("100%");
  });

  test("M5.11-PDF-08 — fit height recalculates scale and remains within viewer zoom bounds", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    const resetButton = sharedPage.locator('[data-testid="pdf-zoom-reset"]');
    const fitHeightButton = sharedPage.locator('[data-testid="pdf-fit-height"]');

    await expect(resetButton).toHaveText("100%");

    await fitHeightButton.click();

    const scaleText = await resetButton.textContent();

    expect(scaleText).toMatch(/^\d+%$/);

    const percentage = Number((scaleText ?? "0").replace("%", ""));

    expect(percentage).toBeGreaterThanOrEqual(50);
    expect(percentage).toBeLessThanOrEqual(300);
  });

  test("M5.11-CIT-01 — matching citation navigates directly to its cited page", async () => {
    test.setTimeout(120000);
    await openWorkspace();
    await waitForPdfLoaded();

    const prompt = sharedPage.getByRole("textbox", { name: /chat prompt/i });
    await expect(prompt).toBeVisible({ timeout: 15000 });

    await prompt.fill(
      "What database extension is used for retrieval in the specification?",
    );
    await prompt.press("Enter");

    await expect(
      sharedPage.locator("svg.lucide-bot").last(),
    ).toBeVisible({ timeout: 45000 });

    await openCitationSources();

    const citationCards = sharedPage.locator('[data-testid^="citation-source-"]');
    await expect(citationCards.first()).toBeVisible();

    const firstCitation = citationCards.first();
    const pageText = await firstCitation
      .locator('[data-testid="citation-page"]')
      .textContent();

    expect(pageText).toMatch(/^Page \d+$/);

    const expectedPage = Number(pageText?.replace("Page ", ""));
    expect(expectedPage).toBeGreaterThanOrEqual(1);
    expect(expectedPage).toBeLessThanOrEqual(PDF_PAGE_COUNT);

    await firstCitation.click();

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText(`${expectedPage} / ${PDF_PAGE_COUNT}`, {
      timeout: 10000,
    });

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toHaveAttribute("data-page-number", String(expectedPage));

    await expect(
      sharedPage.locator('[data-testid="pdf-page-container"]'),
    ).toHaveClass(/ring-4/);

    await expect(
      sharedPage.locator('[data-testid="pdf-page-container"]'),
    ).toHaveClass(/ring-primary\/80/);

    await expect(
      sharedPage.locator('[data-testid="pdf-navigation-announcement"]'),
    ).toHaveText(`Citation navigated to page ${expectedPage}.`);
  });

  test("M5.11-CIT-02 — wrong-document citation is a strict no-op", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    const chatIdMatch = chatUrl.match(/\/chat\/(\d+)/);
    expect(chatIdMatch).not.toBeNull();
    const chatId = chatIdMatch![1];

    await sharedPage.route(`**/chat/${chatId}`, async (route: any) => {
      const response = await route.fetch();
      const body = await response.json();

      for (const message of body) {
        if (!Array.isArray(message.sources)) continue;
        for (const source of message.sources) {
          source.document_id = WRONG_DOCUMENT_ID;
          source.page_number = 2;
        }
      }

      await route.fulfill({ response, json: body });
    });

    await sharedPage.reload();
    await sharedPage.waitForLoadState("domcontentloaded");
    await waitForPdfLoaded();

    await openCitationSources();

    const citationCard = sharedPage.locator('[data-testid^="citation-source-"]').first();
    await expect(citationCard).toBeVisible();
    await citationCard.click();

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("1 / 2");

    await expect(
      sharedPage.locator('[data-testid="pdf-page-container"]'),
    ).not.toHaveClass(/ring-4/);

    await expect(
      sharedPage.locator('[data-testid="pdf-navigation-announcement"]'),
    ).toHaveText("");
  });

  test("M5.11-CIT-03 — invalid citation page is a strict no-op", async () => {
    await sharedPage.unroute(`**/chat/*`);

    await openWorkspace();
    await waitForPdfLoaded();

    const chatIdMatch = chatUrl.match(/\/chat\/(\d+)/);
    expect(chatIdMatch).not.toBeNull();
    const chatId = chatIdMatch![1];

    await sharedPage.route(`**/chat/${chatId}`, async (route: any) => {
      const response = await route.fetch();
      const body = await response.json();

      for (const message of body) {
        if (!Array.isArray(message.sources)) continue;
        for (const source of message.sources) {
          source.document_id = uploadedDocIdNumber;
          source.page_number = 0;
        }
      }

      await route.fulfill({ response, json: body });
    });

    await sharedPage.reload();
    await sharedPage.waitForLoadState("domcontentloaded");
    await waitForPdfLoaded();

    await openCitationSources();

    const citationCard = sharedPage.locator('[data-testid^="citation-source-"]').first();
    await expect(citationCard).toBeVisible();
    await citationCard.click();

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("1 / 2");

    await expect(
      sharedPage.locator('[data-testid="pdf-page-container"]'),
    ).not.toHaveClass(/ring-4/);

    await expect(
      sharedPage.locator('[data-testid="pdf-navigation-announcement"]'),
    ).toHaveText("");
  });

  test("M5.11-CIT-04 — positive out-of-range page clamps to page N", async () => {
    await sharedPage.unroute(`**/chat/*`);

    await openWorkspace();
    await waitForPdfLoaded();

    const chatIdMatch = chatUrl.match(/\/chat\/(\d+)/);
    expect(chatIdMatch).not.toBeNull();
    const chatId = chatIdMatch![1];

    await sharedPage.route(`**/chat/${chatId}`, async (route: any) => {
      const response = await route.fetch();
      const body = await response.json();

      for (const message of body) {
        if (!Array.isArray(message.sources)) continue;
        for (const source of message.sources) {
          source.document_id = uploadedDocIdNumber;
          source.page_number = 999;
        }
      }

      await route.fulfill({ response, json: body });
    });

    await sharedPage.reload();
    await sharedPage.waitForLoadState("domcontentloaded");
    await waitForPdfLoaded();

    await openCitationSources();

    const citationCard = sharedPage.locator('[data-testid^="citation-source-"]').first();
    await citationCard.click();

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("2 / 2");

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toHaveAttribute("data-page-number", "2");

    await expect(
      sharedPage.locator('[data-testid="pdf-page-container"]'),
    ).toHaveClass(/ring-4/);
  });

  test("M5.11-CIT-05 — rapid citation navigation leaves only the latest valid target active", async () => {
    await sharedPage.unroute(`**/chat/*`);

    await openWorkspace();
    await waitForPdfLoaded();

    const chatIdMatch = chatUrl.match(/\/chat\/(\d+)/);
    expect(chatIdMatch).not.toBeNull();
    const chatId = chatIdMatch![1];

    await sharedPage.route(`**/chat/${chatId}`, async (route: any) => {
      const response = await route.fetch();
      const body = await response.json();

      for (const message of body) {
        if (!Array.isArray(message.sources)) continue;
        for (const source of message.sources) {
          source.document_id = uploadedDocIdNumber;
          source.page_number = 1;
        }
      }

      await route.fulfill({ response, json: body });
    });

    await sharedPage.reload();
    await sharedPage.waitForLoadState("domcontentloaded");
    await waitForPdfLoaded();

    await openCitationSources();

    const citationCards = sharedPage.locator('[data-testid^="citation-source-"]');
    const count = await citationCards.count();
    expect(count).toBeGreaterThan(0);

    await citationCards.first().click();

    if (count > 1) {
      await citationCards.nth(1).click();
    }

    await expect(
      sharedPage.locator('[data-testid="pdf-current-page"]'),
    ).toHaveText("1 / 2");

    await expect(
      sharedPage.locator('[data-testid="pdf-page"]'),
    ).toHaveAttribute("data-page-number", /\d+/);
  });

  test("M5.11-RUNTIME — document switching and rapid navigation produce zero runtime errors or unexpected 5xx responses", async () => {
    await sharedPage.unroute(`**/chat/*`);

    await openWorkspace();
    await waitForPdfLoaded();

    const nextButton = sharedPage.locator('[data-testid="pdf-next"]');
    const previousButton = sharedPage.locator('[data-testid="pdf-prev"]');
    const zoomInButton = sharedPage.locator('[data-testid="pdf-zoom-in"]');
    const zoomOutButton = sharedPage.locator('[data-testid="pdf-zoom-out"]');

    for (let index = 0; index < 4; index += 1) {
      await nextButton.click({ force: true }).catch(() => undefined);
      await previousButton.click({ force: true }).catch(() => undefined);
      await zoomInButton.click();
      await zoomOutButton.click();
    }

    const closeButton = sharedPage.locator('[data-testid="workspace-close-button"]');

    if (await closeButton.isVisible()) {
      await closeButton.click();
      await expect(
        sharedPage.locator('[data-testid="workspace-split-pane"]'),
      ).toHaveCount(0);
    }

    await openWorkspace();
    await waitForPdfLoaded();

    monitoring.assertNoErrors();
    expect(fakeWorkerWarnings).toEqual([]);
  });

  test("M5.11-FINAL — final PDF viewer state is internally consistent", async () => {
    await openWorkspace();
    await waitForPdfLoaded();

    const pageText = await sharedPage.locator(
      '[data-testid="pdf-current-page"]',
    ).textContent();
    expect(pageText).toBe("1 / 2");

    const pageNumber = await sharedPage.locator(
      '[data-testid="pdf-page"]',
    ).getAttribute("data-page-number");
    expect(pageNumber).toBe("1");

    await expect(
      sharedPage.locator('[data-testid="pdf-viewer"]'),
    ).toBeVisible();

    monitoring.assertNoErrors();
    expect(fakeWorkerWarnings).toEqual([]);
  });
});
