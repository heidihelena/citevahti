/* 3 · Playwright — the full user flow against the REAL panel + server (a throwaway copy of
 * the demo ledger). Everything is driven by what the user sees, in a real browser. */
import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => { await page.goto("/"); });

test("lands on the review workspace with the claims queue and the primary action", async ({ page }) => {
  await expect(page.locator("#runTests")).toHaveText(/Check claims/);   // the one primary CTA, as the user reads it
  await expect(page.locator("#triagebar")).toContainText(/claim/i);     // the persistent queue
});

test("the queue toggles to All claims and a claim opens its review card", async ({ page }) => {
  await page.getByRole("button", { name: /All claims/ }).click();
  const row = page.locator(".qrow").first();
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.locator("#card")).toContainText(/Rate|Decide|Write|Decision|Edit claim/);
});

test("every surface is reachable from the header nav", async ({ page }) => {
  const tabs = [
    ["Checks", /Claim checks|Maintenance|Run/i],
    ["Atlas", /evidence map|Atlas/i],
    ["Output", /review record/i],
    ["Settings", /AI second opinion|theme|Updates/i],
    ["Manuscripts", /manuscript|review/i],
  ];
  for (const [name, marker] of tabs) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator("main")).toContainText(marker);
  }
});

test("the review record opens as a timestamped timeline and Escape closes it", async ({ page }) => {
  await page.getByRole("button", { name: /Review record/ }).click();
  const dlg = page.getByRole("dialog");
  await expect(dlg).toBeVisible();
  await expect(dlg).toContainText(/Recorded a decision|Claim added|Project created|Recorded a support rating/);
  await page.keyboard.press("Escape");
  await expect(dlg).toBeHidden();
});

test("exporting the review record produces a result the reviewer can locate", async ({ page }) => {
  await page.getByRole("button", { name: "Output", exact: true }).click();
  await page.getByRole("button", { name: /Review record \(\.zip\)/ }).click();   // writes to the temp ledger
  // a result card naming the file + Show in Finder (we don't click it — that would open Finder)
  await expect(page.locator("#outputResult")).toContainText(/Saved|Review record/);
  await expect(page.locator('#outputResult [data-act="reveal"]')).toBeVisible();
});
