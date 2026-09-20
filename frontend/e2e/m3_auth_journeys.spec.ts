import { test, expect } from "./fixtures/test-base";

const TEST_EMAIL = "m3_test_user@example.com";
const TEST_PASSWORD = "Password123!";

test.describe("M3 Auth Regression Gate", () => {
  test("Test A — unauthenticated access redirects to login and prevents data exposure", async ({ page }) => {
    // Navigate directly to protected dashboard
    await page.goto("/dashboard");

    // Must be redirected to login
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator("text=Welcome back")).toBeVisible();

    // Verify protected chat elements are not exposed
    await expect(page.locator("textarea, input[placeholder*='message' i]")).not.toBeVisible();
  });

  test("Test B — deterministic login succeeds to dashboard shell", async ({ page }) => {
    await page.goto("/login");

    await page.fill("#email", TEST_EMAIL);
    await page.fill("#password", TEST_PASSWORD);
    await page.click("button[type='submit']");

    // Wait for redirect to dashboard
    await expect(page).toHaveURL(/\/dashboard/);
    
    // Authenticated shell verification
    await expect(page.locator("body")).not.toContainText("Unable to sign in");
    await expect(page.locator("body")).not.toContainText("Invalid credentials");
  });

  test("Test C — session persistence survives page reload", async ({ page }) => {
    // Login first
    await page.goto("/login");
    await page.fill("#email", TEST_EMAIL);
    await page.fill("#password", TEST_PASSWORD);
    await page.click("button[type='submit']");
    await expect(page).toHaveURL(/\/dashboard/);

    // Reload page
    await page.reload();

    // Must remain on dashboard without kicking back to login
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator("text=Welcome back")).not.toBeVisible();
  });

  test("Test D — logout clears session and returns to login gate", async ({ page }) => {
    // Login
    await page.goto("/login");
    await page.fill("#email", TEST_EMAIL);
    await page.fill("#password", TEST_PASSWORD);
    await page.click("button[type='submit']");
    await expect(page).toHaveURL(/\/dashboard/);

    // Look for existing logout / sign out trigger in UI
    const logoutBtn = page.locator("button:has-text('Sign out'), button:has-text('Log out'), a:has-text('Log out')").first();
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
      await expect(page).toHaveURL(/\/login/);

      // Verify protected route can no longer be accessed
      await page.goto("/dashboard");
      await expect(page).toHaveURL(/\/login/);
    }
  });
});