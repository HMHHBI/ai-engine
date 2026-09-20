import { test as base, expect } from "@playwright/test";

export const test = base.extend({
  page: async ({ page }, use) => {
    const pageErrors: Error[] = [];
    const consoleErrors: string[] = [];
    const server5xxErrors: string[] = [];

    page.on("pageerror", (error) => {
      pageErrors.push(error);
    });

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        const text = msg.text();
        // Ignore expected client aborts or reset during fast test tear-down/reloads
        if (
          !text.includes("net::ERR_CONNECTION_RESET") &&
          !text.includes("net::ERR_ABORTED")
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

    await use(page);

    expect(pageErrors, `Uncaught page errors detected: ${pageErrors.join(", ")}`).toEqual([]);
    expect(consoleErrors, `Console errors detected: ${consoleErrors.join(", ")}`).toEqual([]);
    expect(server5xxErrors, `Unexpected 5xx responses detected: ${server5xxErrors.join(", ")}`).toEqual([]);
  },
});

export { expect };