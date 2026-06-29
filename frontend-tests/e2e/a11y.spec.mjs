/* 5 (interactive) · Playwright — accessibility behaviour that needs a real browser with
 * layout + focus: a named, focus-trapping dialog; and keyboard claim navigation. */
import { test, expect } from "@playwright/test";

test("an open dialog is named, modal, traps Tab, and Escape closes it", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Review record/ }).click();
  const dlg = page.getByRole("dialog");
  await expect(dlg).toBeVisible();
  await expect(dlg).toHaveAttribute("aria-modal", "true");
  await expect(dlg).toHaveAccessibleName(/Review record/);          // labelledby resolves
  for (let i = 0; i < 8; i++) {                                     // Tab stays inside the dialog
    await page.keyboard.press("Tab");
    expect(await dlg.evaluate((d) => d.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dlg).toBeHidden();
});

test("keyboard j/k move the claim selection in the workspace", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /All claims/ }).click();
  await page.locator(".qrow").first().click();
  const first = (await page.locator(".qrow.active").textContent())?.trim();
  await page.keyboard.press("j");
  await expect(page.locator(".qrow.active")).not.toHaveText(first ?? "");   // moved down
  await page.keyboard.press("k");
  await expect(page.locator(".qrow.active")).toHaveText(first ?? "");       // and back
});
