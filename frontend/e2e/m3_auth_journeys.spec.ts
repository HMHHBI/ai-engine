import { test, expect } from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";

test.describe("M3 Auth Regression Gate", () => {
  test("Test A — unauthenticated access redirects to login and prevents data exposure", async ({ page, context }) => {
    await context.clearCookies();
    await page.goto("/dashboard");

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();

    // Verify protected chat elements are not exposed
    await expect(page.locator("textarea, input[placeholder*='message' i]")).not.toBeVisible();
  });

  test("Test B — deterministic login succeeds to dashboard shell", async ({ page }) => {
    await page.goto("/login");

    await page.fill("#email", TEST_EMAIL);
    await page.fill("#password", TEST_PASSWORD);
    await page.click("button[type='submit']");

    await page.waitForURL(/\/dashboard/, { timeout: 20000 });
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator("body")).not.toContainText("Unable to sign in");
    await expect(page.locator("body")).not.toContainText("Invalid credentials");
  });

  test("Test C — session persistence survives page reload", async ({ page }) => {
    await page.goto("/login");
    await page.fill("#email", TEST_EMAIL);
    await page.fill("#password", TEST_PASSWORD);
    await page.click("button[type='submit']");
    await page.waitForURL(/\/dashboard/, { timeout: 20000 });
    await page.waitForLoadState("networkidle");

    await page.reload();

    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("heading", { name: "Welcome back" })).not.toBeVisible();
  });

  test("Test D — logout clears session and returns to login gate", async ({ page }) => {
    await page.goto("/login");
    await page.fill("#email", TEST_EMAIL);
    await page.fill("#password", TEST_PASSWORD);
    await page.click("button[type='submit']");
    await page.waitForURL(/\/dashboard/, { timeout: 20000 });
    await page.waitForLoadState("networkidle");

    const logoutBtn = page.getByRole("button", { name: /log out/i }).or(page.locator("button:has-text('Log out')")).first();
    await expect(logoutBtn).toBeVisible({ timeout: 10000 });
    await logoutBtn.click();

    await page.waitForURL(/\/login/, { timeout: 20000 });
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();

    await page.goto("/dashboard");
    await page.waitForURL(/\/login/, { timeout: 20000 });
    await expect(page).toHaveURL(/\/login/);
  });
});
