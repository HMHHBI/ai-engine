import { test, expect } from "@playwright/test";

test("M3 gate - server is reachable and login page loads", async ({ page }) => {
  const response = await page.goto("/login");
  expect(response?.status()).toBeLessThan(400);
  await expect(page.locator("text=Welcome back")).toBeVisible();
});
