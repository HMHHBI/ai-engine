import { test as base, expect, Page } from "@playwright/test";

export interface PageMonitoringHandle {
  pageErrors: Error[];
  consoleErrors: string[];
  server5xxErrors: string[];
  assertNoErrors: () => void;
}

export function attachPageMonitoring(page: Page): PageMonitoringHandle {
  const pageErrors: Error[] = [];
  const consoleErrors: string[] = [];
  const server5xxErrors: string[] = [];

  page.on("pageerror", (error) => {
    pageErrors.push(error);
  });

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // Filter non-fatal browser network tear-downs
      if (
        !text.includes("net::ERR_CONNECTION_RESET") &&
        !text.includes("net::ERR_ABORTED") &&
        !text.includes("status of 404 (Not Found)")
      ) {
        consoleErrors.push(text);
      }
    }
  });

  page.on("response", (response) => {
    if (response.status() >= 500) {
      server5xxErrors.push(`${response.url()} [${response.status()}]`);
    }
  });

  const assertNoErrors = () => {
    expect(pageErrors, `Uncaught page errors detected: ${pageErrors.join(", ")}`).toEqual([]);
    expect(consoleErrors, `Console errors detected: ${consoleErrors.join(", ")}`).toEqual([]);
    expect(server5xxErrors, `Unexpected 5xx responses detected: ${server5xxErrors.join(", ")}`).toEqual([]);
  };

  return { pageErrors, consoleErrors, server5xxErrors, assertNoErrors };
}

export const test = base.extend({
  page: async ({ page }, use) => {
    const monitoring = attachPageMonitoring(page);
    await use(page);
    monitoring.assertNoErrors();
  },
});

export { expect };
