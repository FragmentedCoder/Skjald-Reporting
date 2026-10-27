import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { setUpAuthenticatorApp, signIn, toastWith, watchForCspViolations } from "./helpers";

const TEMPLATE = "Security incident report";

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/templates-${name}.png`, fullPage: true });
}

function menu(page: Page, name: string) {
  return page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true });
}

async function signedIn(browser: Browser, username: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, username);
  await setUpAuthenticatorApp(page);
  return { context, page };
}

/** The settings panel beside the form. */
const panel = (page: Page) => page.getByRole("complementary", { name: "Settings of what's selected" });
const palette = (page: Page) => page.getByRole("region", { name: "Field types" });

async function addField(page: Page, type: string) {
  await palette(page).getByRole("button", { name: new RegExp(`^${type}`) }).click();
}

async function rename(page: Page, key: string) {
  const field = panel(page).getByLabel("Rules and text read the answer as", { exact: true });
  await field.fill(key);
  await panel(page).getByRole("button", { name: "Rename" }).click();
  await expect(field).toHaveValue(key);
}

/**
 * Drags with the mouse in small steps: svelte-dnd-action only starts a drag after the
 * pointer has moved a little, and follows it move by move.
 */
async function drag(page: Page, from: Locator, to: Locator, { dx = 0, dy = 6 } = {}) {
  await to.scrollIntoViewIfNeeded();
  await from.scrollIntoViewIfNeeded();
  const a = await from.boundingBox();
  const b = await to.boundingBox();
  if (!a || !b) throw new Error("Nothing to drag, or nowhere to drop it.");
  const [sx, sy] = [a.x + a.width / 2, a.y + a.height / 2];
  const [tx, ty] = [b.x + b.width / 2 + dx, b.y + dy];
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  for (let i = 1; i <= 25; i++) await page.mouse.move(sx + ((tx - sx) * i) / 25, sy + ((ty - sy) * i) / 25);
  await page.waitForTimeout(200);
  await page.mouse.up();
}

async function saved(page: Page) {
  await expect(page.getByText(/^Saved at/)).toBeVisible({ timeout: 10_000 });
}

test("a designer builds a template's form, with rules, and publishes it", async ({ browser }) => {
  const { context, page } = await signedIn(browser, "e2e-designer");
  const violations = watchForCspViolations(page);

  await menu(page, "Templates").click();
  await expect(page.getByRole("heading", { name: "Templates" })).toBeVisible();
  await expect(page.getByText("No templates yet.")).toBeVisible();

  // A new template starts with one step and no problems.
  await page.getByRole("button", { name: "New template" }).click();
  await page.getByRole("dialog").getByLabel("Name", { exact: true }).fill(TEMPLATE);
  await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: TEMPLATE })).toBeVisible();
  await expect(page.getByText("No problems", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Step 1: Details, edit" })).toBeVisible();

  // Clicking a field type adds it, selected, with a variable name of its own.
  await addField(page, "Number");
  await panel(page).getByLabel("Question", { exact: true }).fill("Highest CVSS score");
  await rename(page, "cvss");
  await expect(page.getByRole("button", { name: "Highest CVSS score, Number, edit" })).toBeVisible();
  await expect(page.getByText("answers.cvss", { exact: true })).toBeVisible();

  await addField(page, "Yes or no");
  await panel(page).getByLabel("Question", { exact: true }).fill("Was the attacking address found?");
  await rename(page, "attack_found");

  // A rule written by hand is checked as it's typed.
  await addField(page, "Repeating group");
  await panel(page).getByLabel("Question", { exact: true }).fill("Attacking addresses");
  const showWhen = panel(page).getByLabel("Show only when", { exact: true });
  await showWhen.fill("answers.attack_found >= 9");
  await expect(panel(page).getByText(">= doesn't work with yes or no and a whole number.")).toBeVisible();
  await expect(page.getByRole("link", { name: "1 problem" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish" })).toBeDisabled();
  await showWhen.fill("answers.attack_found");
  await expect(panel(page).getByText("Gives yes or no.")).toBeVisible();
  await expect(page.getByText("No problems", { exact: true })).toBeVisible();

  // A calculated value reads another answer; renaming that answer changes it too.
  await addField(page, "Calculated value");
  await panel(page).getByLabel("Question", { exact: true }).fill("Severity");
  await rename(page, "severity");
  await panel(page).getByLabel("Worked out as", { exact: true }).fill('answers.cvss >= 9.0 ? "Critical" : "Lower"');
  await expect(panel(page).getByText("Gives text.")).toBeVisible();
  await page.getByRole("button", { name: "Highest CVSS score, Number, edit" }).click();
  await rename(page, "cvss_score");
  await page.getByRole("button", { name: /^Severity, Calculated value, edit/ }).click();
  await expect(panel(page).getByLabel("Worked out as", { exact: true })).toHaveValue('answers.cvss_score >= 9.0 ? "Critical" : "Lower"');

  // Dragging from the palette drops a new question where it lands; the keyboard moves one.
  await drag(page, palette(page).getByRole("button", { name: /^Short text/ }),
    page.getByRole("button", { name: "Highest CVSS score, Number, edit" }));
  await expect(page.getByRole("button", { name: /^New short text question, Short text, edit/ })).toBeVisible();
  await panel(page).getByLabel("Question", { exact: true }).fill("Summary of the incident");
  await panel(page).getByRole("button", { name: "Move down" }).click();
  const order = page.getByRole("list", { name: "Questions in step 1" }).getByRole("button");
  await expect(order.nth(1)).toHaveAccessibleName(/^Summary of the incident/);

  // A second step, and the settings.
  await page.getByRole("button", { name: "Add a step" }).click();
  await panel(page).getByLabel("Title", { exact: true }).fill("Actions and handover");
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByLabel("Report number prefix", { exact: true }).fill("inc");
  await expect(page.getByLabel("Report number prefix", { exact: true })).toHaveValue("INC");
  await expect(page.getByText(/Reports are numbered INC-\d{4}-0001/)).toBeVisible();
  await page.getByLabel("The technician, then the reviewer", { exact: true }).check();
  await saved(page);
  await shot(page, "settings");

  await page.getByRole("link", { name: "Questions" }).click();
  await saved(page);
  await shot(page, "questions");

  // Publishing freezes version 1; editing starts a new draft from it.
  await page.getByRole("button", { name: "Publish" }).click();
  const dialog = page.getByRole("dialog", { name: "Publish version 1" });
  await dialog.getByLabel(/^What changed/).fill("First version");
  await dialog.getByRole("button", { name: "Publish" }).click();
  await expect(toastWith(page, "Version 1 is published")).toBeVisible();
  await expect(page.getByText("Version 1", { exact: true })).toBeVisible();
  await expect(page.getByText("This is version 1, which reports use.")).toBeVisible();
  await page.getByRole("link", { name: "Versions" }).click();
  await expect(page.getByRole("cell", { name: "First version" })).toBeVisible();
  await page.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByText("Version 1 is the one in use.")).toBeVisible();

  // The templates list says what's published and what's in a draft.
  await page.getByRole("link", { name: "Templates", exact: true }).first().click();
  const row = page.getByRole("row", { name: new RegExp(TEMPLATE) });
  await expect(row.getByText("Version 1")).toBeVisible();
  await expect(row.getByText("Draft", { exact: true })).toBeVisible();
  await shot(page, "list");

  expect(violations).toEqual([]);
  await context.close();
});

test("technicians don't see the builder, and the API refuses them", async ({ browser }) => {
  const { context, page } = await signedIn(browser, "e2e-fitter");
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await expect(menu(page, "Templates")).toHaveCount(0);
  const refused = await page.request.get("/api/templates");
  expect(refused.status()).toBe(403);
  await context.close();
});
