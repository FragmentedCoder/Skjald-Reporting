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

  // A rule built visually is stored as CEL.
  await addField(page, "Repeating group");
  await panel(page).getByLabel("Question", { exact: true }).fill("Attacking addresses");
  const showWhen = panel(page).getByRole("group", { name: "Show only when" });
  await showWhen.getByRole("button", { name: "Add a condition" }).click();
  await showWhen.getByLabel("Show only when 1: what to check").selectOption({ label: "Was the attacking address found?" });
  await expect(showWhen.getByLabel("Show only when 1: how")).toHaveValue("yes");
  await expect(showWhen.getByText("answers.attack_found", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Attacking addresses, Repeating group, edit/ })).toContainText("shown when a rule says so");

  // One written by hand is checked as it's typed, and stays text when the visual editor couldn't have written it.
  await showWhen.getByRole("button", { name: "Edit as text" }).click();
  const text = showWhen.getByRole("textbox");
  await text.fill("answers.attack_found >= 9");
  await expect(showWhen.getByText(">= doesn't work with yes or no and a whole number.")).toBeVisible();
  await expect(page.getByRole("link", { name: "1 problem" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish" })).toBeDisabled();
  await text.fill("answers.attack_found && answers.cvss * 2.0 > 1.0");
  await expect(showWhen.getByText("Written by hand, so it's edited as text.")).toBeVisible();
  await text.fill("answers.attack_found");
  await showWhen.getByRole("button", { name: "Edit visually" }).click();
  await expect(showWhen.getByLabel("Show only when 1: how")).toHaveValue("yes");
  await expect(page.getByText("No problems", { exact: true })).toBeVisible();

  // A calculated value built as IF / ELSE reads another answer; renaming that answer changes it too.
  await addField(page, "Calculated value");
  await panel(page).getByLabel("Question", { exact: true }).fill("Severity");
  await rename(page, "severity");
  const worked = panel(page).getByRole("group", { name: "Worked out as" });
  await worked.getByLabel("Worked out as: how it's worked out").selectOption({ label: "By conditions (IF / ELSE)" });
  await worked.getByLabel("Worked out as, if 1: what to check").selectOption({ label: "Highest CVSS score" });
  await worked.getByLabel("Worked out as, if 1: how").selectOption({ label: "is at least" });
  await worked.getByLabel("Worked out as, if 1: value").fill("9");
  await worked.getByLabel("Worked out as, if: then").fill("Critical");
  await worked.getByLabel("Worked out as: otherwise").fill("Lower");
  await expect(worked.getByText('answers.cvss >= 9.0 ? "Critical" : "Lower"', { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Highest CVSS score, Number, edit" }).click();
  await rename(page, "cvss_score");
  await page.getByRole("button", { name: /^Severity, Calculated value, edit/ }).click();
  await expect(worked.getByText('answers.cvss_score >= 9.0 ? "Critical" : "Lower"', { exact: true })).toBeVisible();
  await expect(worked.getByLabel("Worked out as, if: then")).toHaveValue("Critical");
  await worked.scrollIntoViewIfNeeded();
  await panel(page).screenshot({ path: "e2e-results/screens/templates-rules.png" });

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

test("the library: a technician adds entries, an administrator locks one", async ({ browser }) => {
  const { context, page } = await signedIn(browser, "e2e-librarian");
  const violations = watchForCspViolations(page);
  await menu(page, "Library").click();
  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
  await expect(menu(page, "Templates")).toHaveCount(0);

  await page.getByRole("button", { name: "Add a variable" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name", { exact: true }).fill("support_phone");
  await dialog.getByLabel(/^What it is/).fill("The service desk");
  await dialog.getByLabel("Value", { exact: true }).fill("+45 70 20 30 40");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(toastWith(page, "vars.support_phone is in the library.")).toBeVisible();

  await page.getByRole("button", { name: /^Text snippets/ }).click();
  await page.getByRole("button", { name: "Add a text snippet" }).click();
  await dialog.getByLabel("Name", { exact: true }).fill("handover");
  await dialog.getByLabel("Text", { exact: true }).fill("See {{text.other}}");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(toastWith(page, "A snippet can use variables")).toBeVisible();
  await dialog.getByLabel("Text", { exact: true }).fill("Call {{vars.support_phone}} for the full password.");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: "Call {{vars.support_phone}} for the full password." })).toBeVisible();

  await page.getByRole("button", { name: /^Data tables/ }).click();
  await page.getByRole("button", { name: "Add a data table" }).click();
  await dialog.getByLabel("Name", { exact: true }).fill("severity");
  await dialog.getByRole("button", { name: "Add a row" }).click();
  await dialog.getByLabel("Row 1: key").fill("high");
  await dialog.getByLabel("Row 1: Value").fill("Høj");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: "1 row: Key → Value" })).toBeVisible();

  // An administrator locks the variable; nobody can change it then.
  const { context: adminContext, page: admin } = await signedIn(browser, "e2e-locksmith");
  await menu(admin, "Library").click();
  await admin.getByRole("button", { name: "Actions for vars.support_phone" }).click();
  await admin.getByRole("menuitem", { name: "Lock" }).click();
  await expect(admin.getByRole("row", { name: /vars\.support_phone/ }).getByText("Locked")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Actions for vars.support_phone" }).click();
  await expect(page.getByRole("menuitem", { name: "History" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Change" })).toHaveCount(0);
  expect(violations).toEqual([]);
  await adminContext.close();
  await context.close();
});

test("a designer lays out the PDF and sees its pages", async ({ browser }) => {
  const { context, page } = await signedIn(browser, "e2e-designer2");
  const violations = watchForCspViolations(page);
  await menu(page, "Templates").click();
  await page.getByRole("button", { name: "New template" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill("Storage device destruction");
  await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Storage device destruction" })).toBeVisible();

  // Two questions to print.
  await addField(page, "Short text");
  await panel(page).getByLabel("Question", { exact: true }).fill("Serial numbers");
  await rename(page, "serials");
  await addField(page, "Repeating group");
  await panel(page).getByLabel("Question", { exact: true }).fill("Devices");
  await rename(page, "devices");

  await page.getByRole("link", { name: "Layout" }).click();
  const blocks = page.getByRole("region", { name: "Blocks" });
  await expect(page.getByRole("button", { name: "Section: Summary, edit" })).toBeVisible();

  // Selecting the section and clicking a block adds it inside the section.
  await page.getByRole("button", { name: "Section: Summary, edit" }).click();
  await blocks.getByRole("button", { name: /^Answer/ }).click();
  await panel(page).getByLabel("Answer to print").selectOption({ label: "Serial numbers" });
  await expect(page.getByRole("list", { name: "Blocks in “Summary”" }).getByRole("button", { name: "Answer: Answer, edit" })).toBeVisible();
  await blocks.getByRole("button", { name: /^Table/ }).click();
  await panel(page).getByLabel("Rows from").selectOption({ label: "Devices" });
  await panel(page).getByLabel("Caption", { exact: true }).fill("Devices destroyed");

  // Rich text with a name in it.
  await blocks.getByRole("button", { name: /^Text/ }).click();
  const editor = panel(page).getByRole("textbox", { name: "Text" });
  await editor.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("Destroyed on site for ");
  await panel(page).getByRole("button", { name: "Insert a name" }).click();
  await panel(page).getByLabel("Name to insert").selectOption({ label: "The customer's name" });
  await expect(editor.locator("span.variable")).toHaveText("{{ customer.name }}");
  await panel(page).getByRole("button", { name: "Bold" }).click();
  await page.keyboard.type(" today");
  await expect(editor.locator("strong")).toHaveText("today");
  await page.keyboard.press("ControlOrMeta+b");
  await page.keyboard.type(". ");
  await panel(page).getByRole("button", { name: "Insert a name" }).click();
  await panel(page).getByLabel("Name to insert").selectOption({ label: "handover" });

  // A callout whose tone the answers set; an image uploaded with the template.
  await blocks.getByRole("button", { name: /^Callout/ }).click();
  await panel(page).getByLabel("Title", { exact: true }).fill("Handle with care");
  const tone = panel(page).getByRole("group", { name: "Tone set by the answers" });
  await tone.getByRole("button", { name: "Add a rule" }).click();
  await tone.getByLabel("Tone set by the answers: how it's worked out").selectOption({ label: "By conditions (IF / ELSE)" });
  await tone.getByLabel("Tone set by the answers, if 1: what to check").selectOption({ label: "Devices" });
  await tone.getByLabel("Tone set by the answers, if 1: how").selectOption({ label: "has no rows" });
  await tone.getByLabel("Tone set by the answers, if: then").selectOption({ label: "Critical" });
  await tone.getByLabel("Tone set by the answers: otherwise").selectOption({ label: "Info" });
  await expect(tone.getByText('answers.devices.size() == 0 ? "critical" : "info"', { exact: true })).toBeVisible();

  await blocks.getByRole("button", { name: /^Image/ }).click();
  // An 8 by 6 pixel picture in Fjord blue.
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAGCAIAAABxZ0isAAAAEUlEQVR4nGPQju3CihgGUgIA/LgzYXxR8ZMAAAAASUVORK5CYII=", "base64");
  await panel(page).getByText("Upload an image").locator("input[type=file]").setInputFiles({ name: "network.png", mimeType: "image/png", buffer: png });
  await expect(panel(page).getByLabel("Image", { exact: true })).toHaveValue(/^[0-9a-f]{64}$/);
  await expect(page.getByText("No problems", { exact: true })).toBeVisible();

  // The pages: the section's blocks, the callout critical (no devices yet), the image.
  await page.getByRole("button", { name: "Pages", exact: true }).click();
  const sheet = page.getByRole("region", { name: "Page 1 of 1" });
  await expect(sheet.getByRole("heading", { name: "1 Summary" })).toBeVisible();
  await expect(sheet.getByText("Destroyed on site for Fjordvik Logistik A/S today. Call +45 70 20 30 40 for the full password.")).toBeVisible();
  await expect(sheet.locator("strong", { hasText: "today" })).toBeVisible();
  await expect(sheet.getByText("Table 1. Devices destroyed")).toBeVisible();
  await expect(sheet.locator("aside.callout.tone-critical")).toContainText("Handle with care");
  await expect(sheet.locator("figure.image img")).toBeVisible();
  await saved(page);
  await shot(page, "pages");

  // Saved as the server accepts it: the same after a reload.
  await page.reload();
  await page.getByRole("button", { name: "Pages", exact: true }).click();
  await expect(page.getByRole("region", { name: "Page 1 of 1" }).getByText(/^Destroyed on site for Fjordvik Logistik A\/S today\./)).toBeVisible();

  // Try it: the technician's form beside the PDF, which follows the answers.
  await page.getByRole("link", { name: "Try it" }).click();
  const pdf = page.getByRole("region", { name: "The PDF" });
  await page.getByRole("textbox", { name: "Serial numbers" }).fill("SN-4471");
  await expect(pdf.getByText("SN-4471")).toBeVisible();
  await expect(pdf.locator("aside.callout.tone-critical")).toBeVisible();
  await page.getByRole("button", { name: "Add a row" }).click();
  await page.getByRole("textbox", { name: "Value, row 1" }).fill("Seagate ST4000, SN-4471");
  await expect(pdf.locator("aside.callout.tone-info")).toBeVisible();
  await expect(pdf.getByRole("cell", { name: "Seagate ST4000, SN-4471" })).toBeVisible();
  await page.getByRole("button", { name: "Check the answers" }).click();
  await expect(page.getByText("Nothing missing: a report like this could go for review.")).toBeVisible();
  await saved(page);
  await shot(page, "try-it");

  // The Data tab: every name, with the sample answers; expressions tried on them.
  await page.getByRole("link", { name: "Data" }).click();
  await expect(page.getByRole("row", { name: /answers\.serials Serial numbers text "SN-4471"/ })).toBeVisible();
  await page.getByRole("textbox", { name: "Expression" }).fill("answers.serials.lowerAscii()");
  await expect(page.getByRole("status")).toHaveText('"sn-4471", which is text');
  await page.getByRole("textbox", { name: "Expression" }).fill("answers.serials > 1");
  await expect(page.getByRole("status")).toHaveText("> doesn't work with text and a whole number.");
  expect(violations).toEqual([]);
  await context.close();
});

/** Presses on from and moves to (x, y) in small steps, holding there before dropping, as someone deciding where. */
async function dragTo(page: Page, from: Locator, x: number, y: number, hold = 200) {
  await from.scrollIntoViewIfNeeded();
  const a = await from.boundingBox();
  if (!a) throw new Error("Nothing to drag.");
  const [sx, sy] = [a.x + a.width / 2, a.y + a.height / 2];
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  for (let i = 1; i <= 25; i++) await page.mouse.move(sx + ((x - sx) * i) / 25, sy + ((y - sy) * i) / 25);
  await page.waitForTimeout(hold);
  await page.mouse.up();
}

test("a designer drags blocks in the outline and on the pages", async ({ browser }) => {
  const { context, page } = await signedIn(browser, "e2e-dragger");
  const violations = watchForCspViolations(page);
  const crashes: string[] = [];
  page.on("pageerror", (error) => crashes.push(error.message));
  await menu(page, "Templates").click();
  await page.getByRole("button", { name: "New template" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill("Server room handover");
  await page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Server room handover" })).toBeVisible();

  // A question dragged in and held over the form a while: nothing half-dragged is saved.
  const steps = page.getByRole("list", { name: "Questions in step 1" });
  const s = await steps.boundingBox();
  await dragTo(page, palette(page).getByRole("button", { name: /^Short text/ }), s!.x + s!.width / 2, s!.y + 20, 2500);
  await expect(steps.getByRole("button", { name: /^New short text question, Short text, edit/ })).toBeVisible();
  await saved(page);
  await expect(page.getByText(/isn't valid/)).toHaveCount(0);

  await page.getByRole("link", { name: "Layout" }).click();
  const blocks = page.getByRole("region", { name: "Blocks" });
  const outline = page.getByRole("list", { name: "Blocks in the PDF" });
  await expect(page.getByRole("button", { name: "Section: Summary, edit" })).toBeVisible();

  // A section dropped below the last block goes at the end of the PDF, on a new page.
  const summary = outline.locator(":scope > li").first();
  const card = await summary.boundingBox();
  const below = await outline.boundingBox();
  await dragTo(page, blocks.getByRole("button", { name: /^Section/ }), card!.x + card!.width / 2, below!.y + below!.height + 16, 1500);
  await expect(outline.locator(":scope > li")).toHaveCount(2);
  await expect(outline.locator(":scope > li").nth(1)).toContainText("Section · new page");
  await saved(page);

  // A section dragged onto its own inside isn't lost into itself.
  const own = await summary.boundingBox();
  await dragTo(page, summary.getByRole("button", { name: "Section: Summary, edit" }), own!.x + own!.width / 2, own!.y + own!.height - 12, 800);
  await expect(outline.locator(":scope > li").filter({ has: page.getByRole("button", { name: "Section: Summary, edit" }) })).toHaveCount(1);
  await expect(outline.locator(":scope > li")).toHaveCount(2);

  // Typing {{ in a title suggests names; Enter takes one.
  await page.getByRole("button", { name: "Section: New section, edit" }).click();
  const title = panel(page).getByLabel("Title", { exact: true });
  await title.fill("Findings for ");
  await title.press("End");
  await title.pressSequentially("{{cust");
  await expect(panel(page).getByRole("listbox", { name: "Names" }).getByRole("option").first()).toContainText("customer.name");
  await title.press("Enter");
  await expect(title).toHaveValue("Findings for {{customer.name}}");

  // Clicking Section with a block inside a section selected adds one beside that section.
  await page.getByRole("button", { name: "Section: Summary, edit" }).click();
  await blocks.getByRole("button", { name: /^Signatures/ }).click();
  await blocks.getByRole("button", { name: /^Section/ }).click();
  await expect(outline.locator(":scope > li")).toHaveCount(3);
  await expect(outline.locator(":scope > li").filter({ hasText: "New section" })).toContainText("Section · new page");
  await expect(page.getByRole("list", { name: "Blocks in “Summary”" }).getByRole("button", { name: /^Section/ })).toHaveCount(0);

  // A clicked cover goes first. On the pages it sits right under the style picker, and
  // the signatures look as in the design.
  await blocks.getByRole("button", { name: /^Cover/ }).click();
  await expect(outline.locator(":scope > li").first()).toContainText("Cover");
  await page.getByRole("button", { name: "Pages", exact: true }).click();
  const first = page.getByRole("region", { name: /^Page 1 of / });
  await expect(first.getByRole("heading", { name: "Security incident report" })).toBeVisible();
  const picker = await page.getByLabel("Preview in").boundingBox();
  const sheet = await first.boundingBox();
  expect(sheet!.y - (picker!.y + picker!.height)).toBeLessThan(40);
  const signed = page.getByRole("region", { name: /^Page 2 of / });
  await expect(signed.getByText("Freja Holm", { exact: true })).toBeVisible();
  await expect(signed.getByText("Sample signatures. In the PDF each one is a digital signature that can be checked.")).toBeVisible();

  // A block from the palette dropped on a page goes where it lands.
  const findings = page.getByRole("heading", { name: /^\d Findings for Fjordvik Logistik A\/S$/ });
  await findings.scrollIntoViewIfNeeded();
  const h = await findings.boundingBox();
  await dragTo(page, blocks.getByRole("button", { name: /^Callout/ }), h!.x + h!.width / 2, h!.y + h!.height + 12, 600);
  await page.getByRole("button", { name: "Blocks", exact: true }).click();
  await expect(page.getByRole("list", { name: "Blocks in “Findings for {{customer.name}}”" }).getByRole("button", { name: /^Callout/ })).toBeVisible();
  await saved(page);
  await shot(page, "dragged");

  expect(crashes).toEqual([]);
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
