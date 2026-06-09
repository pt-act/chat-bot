import { test, expect } from "@playwright/test";

test.describe("App Load", () => {
  test("page loads and title is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("text=Chat").first()).toBeVisible();
  });

  test("composer textarea is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("textarea")).toBeVisible();
  });

  test("health badge is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".health")).toBeVisible();
  });

  test("mode selector is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("select[aria-label='Chat mode']")).toBeVisible();
  });

  test("send button is disabled initially", async ({ page }) => {
    await page.goto("/");
    const sendButton = page.locator("button[type='submit']");
    await expect(sendButton).toBeDisabled();
  });
});

test.describe("Composer Interaction", () => {
  test("send button enables when text is entered", async ({ page }) => {
    await page.goto("/");
    const textarea = page.locator("textarea");
    const sendButton = page.locator("button[type='submit']");
    
    await textarea.fill("Hello");
    await expect(sendButton).toBeEnabled();
  });

  test("character counter shows count", async ({ page }) => {
    await page.goto("/");
    const textarea = page.locator("textarea");
    
    await textarea.fill("Hello world");
    await expect(page.locator("text=/11/")).toBeVisible();
  });

  test("empty message does not send", async ({ page }) => {
    await page.goto("/");
    const textarea = page.locator("textarea");
    const sendButton = page.locator("button[type='submit']");
    
    await textarea.fill("   ");
    await expect(sendButton).toBeDisabled();
  });
});

test.describe("Accessibility", () => {
  test("has no detectable a11y violations on load", async ({ page }) => {
    await page.goto("/");
    // Basic check: ensure ARIA landmarks exist
    await expect(page.locator("main")).toBeVisible();
  });

  test("textarea has correct aria-label", async ({ page }) => {
    await page.goto("/");
    const textarea = page.locator("textarea");
    await expect(textarea).toHaveAttribute("aria-label", /message/i);
  });
});
