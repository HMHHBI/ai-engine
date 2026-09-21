import { test as baseTest, expect, Page } from "@playwright/test";

export interface PageMonitoringHandle {
  pageErrors: Error[];
  consoleErrors: string[];
  server5xxErrors: string[];
  assertNoErrors: () => void;
}

export function setupPageMonitoring(page: Page): PageMonitoringHandle {
  const pageErrors: Error[] = [];
  const consoleErrors: string[] = [];
  const server5xxErrors: string[] = [];

  page.on("pageerror", (error) => {
    pageErrors.push(error);
  });

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // Filter browser network-level status logs for expected 404/aborted requests
      if (
        !text.includes("net::ERR_CONNECTION_RESET") &&
        !text.includes("net::ERR_ABORTED") &&
        !text.includes("Failed to load resource: the server responded with a status of 404") &&
        !text.includes("Failed to load resource: the server responded with a status of 403")
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

export const attachPageMonitoring = setupPageMonitoring;
export const test = baseTest;
export { expect };
