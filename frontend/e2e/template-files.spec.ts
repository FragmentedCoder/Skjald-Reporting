import { expect, test } from "@playwright/test";
import { dismissToasts, setUpAuthenticatorApp, signIn, toastWith, watchForCspViolations } from "./helpers";

test("a template goes out as a .skjald file and comes back, and a copy is translated", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, "e2e-mover");
  await setUpAuthenticatorApp(page);
  const violations = watchForCspViolations(page);

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Templates", exact: true }).click();
  await page.getByRole("button", { name: "New template" }).click();
  await page.getByRole("dialog").getByLabel("Name", { exact: true }).fill("Firewall change");
  await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Firewall change" })).toBeVisible();

  // The Strings tab: every piece of text on one page.
  await page.getByRole("link", { name: "Strings" }).click();
  const summary = page.getByRole("region", { name: "Section block “Summary”" }).getByLabel("Title");
  await summary.fill("What was changed");
  await summary.press("Tab");
  await expect(page.getByText(/^Saved at/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("region", { name: "Section block “What was changed”" })).toBeVisible();

  // Out as a file, and back in as a new template's draft.
  await page.getByRole("link", { name: "Versions" }).click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Export the draft" }).click()]);
  expect(download.suggestedFilename()).toBe("firewall-change-draft.skjald");
  const file = await download.path();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Templates", exact: true }).click();
  await page.getByLabel("Import", { exact: true }).setInputFiles(file);
  await expect(toastWith(page, "“Firewall change (imported)” is imported as a draft")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Firewall change (imported)" })).toBeVisible();
  await page.getByRole("link", { name: "Strings" }).click();
  await expect(page.getByRole("region", { name: "Section block “What was changed”" })).toBeVisible();

  // A file that isn't one is refused plainly.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Templates", exact: true }).click();
  await dismissToasts(page);
  await page.getByLabel("Import", { exact: true }).setInputFiles({ name: "notes.skjald", mimeType: "application/zip", buffer: Buffer.from("not a zip") });
  await expect(toastWith(page, "That isn't a Skjald template file.")).toBeVisible();

  // Copied for translation: a Danish draft, opened on its Strings tab.
  await page.getByRole("row", { name: /^Firewall change\b(?! \()/ }).getByRole("button", { name: /^Actions for/ }).click();
  await page.getByRole("menuitem", { name: "Copy for translation" }).click();
  const dialog = page.getByRole("dialog", { name: "Copy for translation" });
  await dialog.getByLabel("Name of the copy").fill("Ændring af firewall");
  await expect(dialog.getByLabel("Report language")).toHaveValue("da");
  await dialog.getByRole("button", { name: "Copy" }).click();
  await expect(page.getByRole("heading", { name: "Ændring af firewall" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Strings" })).toHaveAttribute("aria-current", "page");
  await page.getByRole("region", { name: "Step “Details”" }).getByLabel("Title").fill("Detaljer");
  await page.getByRole("region", { name: "Step “Details”" }).getByLabel("Title").press("Tab");
  await expect(page.getByRole("region", { name: "Step “Detaljer”" })).toBeVisible();
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByLabel("Language for dates and numbers")).toHaveValue("da");

  expect(violations).toEqual([]);
  await context.close();
});
