# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: web/e2e/app.spec.ts >> App Load >> health badge is visible
- Location: web/e2e/app.spec.ts:14:2

# Error details

```
Error: goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | 
  3  | test.describe("App Load", () => {
  4  |   test("page loads and title is visible", async ({ page }) => {
  5  |     await page.goto("/");
  6  |     await expect(page.locator("text=Chat").first()).toBeVisible();
  7  |   });
  8  | 
  9  |   test("composer textarea is visible", async ({ page }) => {
  10 |     await page.goto("/");
  11 |     await expect(page.locator("textarea")).toBeVisible();
  12 |   });
  13 | 
  14 |   test("health badge is visible", async ({ page }) => {
> 15 |     await page.goto("/");
     |               ^ Error: goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  16 |     await expect(page.locator("[data-testid='health-badge']")).toBeVisible();
  17 |   });
  18 | 
  19 |   test("mode selector is visible", async ({ page }) => {
  20 |     await page.goto("/");
  21 |     await expect(page.locator("[data-testid='mode-selector']")).toBeVisible();
  22 |   });
  23 | 
  24 |   test("send button is disabled initially", async ({ page }) => {
  25 |     await page.goto("/");
  26 |     const sendButton = page.locator("button[type='submit']");
  27 |     await expect(sendButton).toBeDisabled();
  28 |   });
  29 | });
  30 | 
  31 | test.describe("Composer Interaction", () => {
  32 |   test("send button enables when text is entered", async ({ page }) => {
  33 |     await page.goto("/");
  34 |     const textarea = page.locator("textarea");
  35 |     const sendButton = page.locator("button[type='submit']");
  36 |     
  37 |     await textarea.fill("Hello");
  38 |     await expect(sendButton).toBeEnabled();
  39 |   });
  40 | 
  41 |   test("character counter shows count", async ({ page }) => {
  42 |     await page.goto("/");
  43 |     const textarea = page.locator("textarea");
  44 |     
  45 |     await textarea.fill("Hello world");
  46 |     await expect(page.locator("text=/11/")).toBeVisible();
  47 |   });
  48 | 
  49 |   test("empty message does not send", async ({ page }) => {
  50 |     await page.goto("/");
  51 |     const textarea = page.locator("textarea");
  52 |     const sendButton = page.locator("button[type='submit']");
  53 |     
  54 |     await textarea.fill("   ");
  55 |     await expect(sendButton).toBeDisabled();
  56 |   });
  57 | });
  58 | 
  59 | test.describe("Accessibility", () => {
  60 |   test("has no detectable a11y violations on load", async ({ page }) => {
  61 |     await page.goto("/");
  62 |     // Basic check: ensure ARIA landmarks exist
  63 |     await expect(page.locator("main")).toBeVisible();
  64 |   });
  65 | 
  66 |   test("textarea has correct aria-label", async ({ page }) => {
  67 |     await page.goto("/");
  68 |     const textarea = page.locator("textarea");
  69 |     await expect(textarea).toHaveAttribute("aria-label", /message/i);
  70 |   });
  71 | });
  72 | 
```