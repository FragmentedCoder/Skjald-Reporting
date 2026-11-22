import { expect, test, type Browser, type Page } from "@playwright/test";
import { setUpAuthenticatorApp, signIn, toastWith, totp, watchForCspViolations } from "./helpers";

// A report from start to discard: started by a technician, written by two of them in
// steps of their own, checked, and its checkouts released and ended. The template,
// the customer and the project are made through the API, as an administrator would
// set them up; everything about the report itself is done on its pages.

const TEMPLATE = "Storage check";
const CUSTOMER = "Vesterhav Fragt A/S";
const PROJECT = "Server room inspection";
const SECRET = "Sommer2026!Fjord";

const CONTENT = {
  schema: 1,
  settings: { prefix: "CHK" },
  form: [
    { id: "s_visit", title: "Visit", questions: [
      { id: "q_checked", key: "checked", type: "text", label: "What was checked", required: true },
      { id: "q_result", key: "result", type: "dropdown", label: "Result",
        settings: { options: [{ value: "ok", label: "In order" }, { value: "faults", label: "Faults found" }] } },
      { id: "q_day", key: "day", type: "datetime", label: "Day of the visit", settings: { mode: "date" } },
      { id: "q_disks", key: "disks", type: "repeating", label: "Disks", settings: { columns: [
        { key: "serial", label: "Serial", type: "text" },
        { key: "size", label: "Size", type: "number", settings: { whole: true } },
      ] } },
      { id: "q_console", key: "console", type: "secret", label: "Console password" },
    ] },
    { id: "s_followup", title: "Follow-up", questions: [
      { id: "q_next", key: "next", type: "text", label: "What to do next", required: true },
    ] },
  ],
  layout: [{ id: "b_summary", kind: "section", title: "Summary", new_page: false,
    blocks: [{ id: "b_checked", kind: "answer", question: "q_checked" }] }],
};

interface Created {
  id: number;
}

interface Customer extends Created {
  assignable: { id: number; username: string }[];
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/reports-${name}.png`, fullPage: true });
}

function menu(page: Page, name: string) {
  return page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true });
}

/** Someone signed in, in a browser of their own, with an authenticator app set up. */
async function signedIn(browser: Browser, username: string, options: { clock?: boolean } = {}) {
  const context = await browser.newContext();
  // A clock the test can move on, for what the page asks every twenty seconds.
  if (options.clock) await context.clock.install();
  const page = await context.newPage();
  await signIn(page, username);
  const secret = await setUpAuthenticatorApp(page);
  return { context, page, secret };
}

/** Calls the API as the page's signed-in user, CSRF token included. */
async function call<T>(page: Page, method: string, path: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ({ method, path, body }) => {
      const session = await (await fetch("/api/auth/session")).json();
      const response = await fetch(`/api${path}`, {
        method,
        headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${await response.text()}`);
      return response.json();
    },
    { method, path, body },
  );
}

/** The answers changed last are saved: the header says when. */
async function saved(page: Page) {
  await expect(page.getByText(/^Saved \d{2}:\d{2}$/)).toBeVisible({ timeout: 10_000 });
}

const form = (page: Page) => page.getByRole("region", { name: "The form" });
const held = (page: Page) => page.getByRole("region", { name: "Checked out" });
const preview = (page: Page) => page.getByRole("region", { name: "Preview" });
const stepButton = (page: Page, title: string) => form(page).getByRole("list", { name: "Steps" }).getByRole("button", { name: title });
/** One question's part of the form: its group, named by its label. */
const question = (page: Page, label: string) => form(page).getByRole("group", { name: label });

test("a report is started, written by two technicians in steps of their own, checked and discarded", async ({ browser }) => {
  test.setTimeout(240_000);

  // An administrator publishes a small template, and sets up a customer and a project
  // with one technician responsible and another on its team.
  const admin = await signedIn(browser, "e2e-arranger");
  const template = await call<Created>(admin.page, "POST", "/templates", { name: TEMPLATE });
  const draft = await call<{ revision: number; problems: unknown[] }>(admin.page, "PUT", `/templates/${template.id}/draft`,
    { content: CONTENT, revision: 1 });
  expect(draft.problems).toEqual([]);
  await call(admin.page, "POST", `/templates/${template.id}/publish`, { revision: draft.revision, note: "First version" });
  const customer = await call<Customer>(admin.page, "POST", "/customers", { name: CUSTOMER, cvr: "44556677", address: "Kajvej 4\n6700 Esbjerg" });
  const idOf = (username: string) => customer.assignable.find((p) => p.username === username)!.id;
  await call(admin.page, "PUT", `/customers/${customer.id}/assignments`, { technicians: [idOf("e2e-reporter"), idOf("e2e-writer")] });
  const project = await call<Created>(admin.page, "POST", `/customers/${customer.id}/projects`,
    { name: PROJECT, classification: "TLP:AMBER", responsible_id: idOf("e2e-reporter"), start_date: "2026-11-02" });
  await call(admin.page, "PUT", `/projects/${project.id}/team`, { technicians: [idOf("e2e-writer")] });

  // The responsible technician finds no reports yet, and starts one with the template.
  const runa = await signedIn(browser, "e2e-reporter", { clock: true });
  const violations = watchForCspViolations(runa.page);
  // A technician may not read styles: the preview mustn't ask for them.
  const refused: string[] = [];
  runa.page.on("response", (response) => {
    if (response.status() === 403) refused.push(response.url());
  });
  await runa.page.goto(`/projects/${project.id}`);
  await expect(runa.page.getByRole("heading", { name: PROJECT })).toBeVisible();
  await expect(runa.page.getByRole("region", { name: "Reports" }).getByText("No reports yet.")).toBeVisible();
  await runa.page.getByRole("button", { name: "New report" }).click();
  const starting = runa.page.getByRole("dialog", { name: "New report" });
  await starting.getByLabel("Template").selectOption({ label: `${TEMPLATE} (version 1)` });
  await expect(starting.getByText("the next number that starts with CHK")).toBeVisible();
  await starting.getByLabel("Title").fill("Server room, November");
  await shot(runa.page, "1-new-report");
  await starting.getByRole("button", { name: "Start the report" }).click();

  // The report opens: its header, and the side menu on its project with Reports marked.
  await expect(runa.page).toHaveURL(/\/reports\/\d+$/);
  const reportUrl = new URL(runa.page.url()).pathname;
  await expect(runa.page.getByRole("heading", { name: "Server room, November", level: 1 })).toBeVisible();
  const tags = runa.page.locator(".tags");
  await expect(tags.getByText(/^CHK-\d{4}-\d{4}$/)).toBeVisible();
  const number = ((await tags.getByText(/^CHK-\d{4}-\d{4}$/).textContent()) ?? "").trim();
  await expect(tags.getByText("Draft", { exact: true })).toBeVisible();
  await expect(tags.getByText(`${TEMPLATE}, version 1`)).toBeVisible();
  await expect(tags.getByRole("link", { name: PROJECT })).toBeVisible();
  await expect(tags.getByRole("link", { name: CUSTOMER })).toBeVisible();
  await expect(menu(runa.page, "Reports")).toHaveAttribute("aria-current", "page");

  // Nothing can be changed until a step is checked out.
  await expect(held(runa.page)).toContainText("Nobody has this report checked out.");
  const checked = form(runa.page).getByRole("textbox", { name: "What was checked" });
  await expect(checked).toBeDisabled();
  await expect(form(runa.page).getByRole("button", { name: "Add a row" })).toHaveCount(0);
  await form(runa.page).getByRole("button", { name: "Check out this step" }).click();
  await expect(form(runa.page).getByText("You have this step checked out.")).toBeVisible();
  await expect(held(runa.page).getByRole("listitem")).toContainText("You have the step “Visit” since");
  await expect(checked).toBeEnabled();

  // A few kinds of answer, saved as they're typed. The preview follows them.
  await checked.fill("Both racks in the server room");
  await form(runa.page).getByRole("combobox", { name: "Result" }).selectOption({ label: "Faults found" });
  await question(runa.page, "Day of the visit").locator("input").fill("2026-11-20");
  await form(runa.page).getByRole("button", { name: "Add a row" }).click();
  await form(runa.page).getByRole("textbox", { name: "Serial, row 1" }).fill("WD-4471");
  await form(runa.page).getByRole("spinbutton", { name: "Size, row 1" }).fill("4000");
  const password = question(runa.page, "Console password");
  await password.locator("input").fill(SECRET);
  await saved(runa.page);
  await expect(preview(runa.page).getByText("Both racks in the server room")).toBeVisible();
  await expect(preview(runa.page).getByText("Drawn in your browser as you type.")).toBeVisible();
  // Drawn in the Skjald default, with no style to pick and nothing refused.
  await expect(preview(runa.page).getByText("Preview in")).toHaveCount(0);
  await expect(preview(runa.page).getByText(/couldn't load the styles/)).toHaveCount(0);
  await shot(runa.page, "2-filled-in");

  // The title is changed in place, by whoever holds a checkout.
  await runa.page.getByRole("button", { name: "Change the title" }).click();
  await runa.page.getByLabel("Title", { exact: true }).fill("Server room check, November");
  await runa.page.getByRole("button", { name: "Save the title" }).click();
  await expect(runa.page.getByRole("heading", { name: "Server room check, November", level: 1 })).toBeVisible();

  // Reloaded, the answers are there, the step is still hers (leaving doesn't release
  // it), and the secret is only said to be filled in.
  await runa.page.reload();
  await expect(checked).toHaveValue("Both racks in the server room");
  await expect(checked).toBeEnabled();
  await expect(form(runa.page).getByRole("combobox", { name: "Result" })).toHaveValue("faults");
  await expect(question(runa.page, "Day of the visit").locator("input")).toHaveValue("2026-11-20");
  await expect(form(runa.page).getByRole("textbox", { name: "Serial, row 1" })).toHaveValue("WD-4471");
  await expect(form(runa.page).getByRole("spinbutton", { name: "Size, row 1" })).toHaveValue("4000");
  await expect(password.getByText("Filled in. Its value isn't shown.")).toBeVisible();
  await expect(password.locator("input")).toHaveCount(0);
  await expect(runa.page.getByText(SECRET)).toHaveCount(0);
  expect(await runa.page.content()).not.toContain(SECRET);

  // The project's list of reports, as the second technician finds it.
  const vigga = await signedIn(browser, "e2e-writer");
  await vigga.page.goto(`/projects/${project.id}`);
  const row = vigga.page.getByRole("row").filter({ has: vigga.page.getByRole("link", { name: number }) });
  await expect(row).toContainText("Server room check, November");
  await expect(row).toContainText(`${TEMPLATE}, version 1`);
  await expect(row).toContainText("Draft");
  await expect(row).toContainText("Runa Reporter");
  await shot(vigga.page, "3-list");
  await row.getByRole("link", { name: number }).click();
  await expect(vigga.page).toHaveURL(new RegExp(`${reportUrl}$`));

  // She sees who holds the first step, and can read it but not change it.
  await expect(held(vigga.page).getByRole("listitem")).toContainText("Runa Reporter has the step “Visit” since");
  await expect(form(vigga.page).getByText("Runa Reporter has this step checked out")).toBeVisible();
  const read = form(vigga.page).getByRole("textbox", { name: "What was checked" });
  await expect(read).toHaveValue("Both racks in the server room");
  await expect(read).toBeDisabled();
  await expect(form(vigga.page).getByRole("button", { name: "Add a row" })).toHaveCount(0);
  await expect(form(vigga.page).getByRole("button", { name: "Check out this step" })).toHaveCount(0);
  await expect(question(vigga.page, "Console password").getByText("Filled in. Its value isn't shown.")).toBeVisible();
  await expect(question(vigga.page, "Console password").getByRole("button", { name: "Replace" })).toHaveCount(0);

  // She takes the other step. "Check the answers" lists its required question, left empty.
  await stepButton(vigga.page, "Follow-up").click();
  await form(vigga.page).getByRole("button", { name: "Check out this step" }).click();
  await expect(form(vigga.page).getByText("You have this step checked out.")).toBeVisible();
  await form(vigga.page).getByRole("button", { name: "Check the answers" }).click();
  const review = vigga.page.getByRole("region", { name: "Before it can go for review" });
  await expect(review.getByRole("listitem")).toHaveCount(1);
  await expect(review.getByRole("listitem")).toContainText("is required.");
  await expect(review.getByRole("button", { name: "What to do next" })).toBeVisible();
  await shot(vigga.page, "4-missing");

  // Answered and saved, nothing is missing any more.
  await form(vigga.page).getByRole("textbox", { name: "What to do next" }).fill("Replace the disk in rack B");
  await saved(vigga.page);
  await form(vigga.page).getByRole("button", { name: "Check the answers" }).click();
  await expect(review.getByText("Nothing missing.")).toBeVisible();

  // The first technician's page notices, at its next look: who holds the other step, and what was saved there.
  await stepButton(runa.page, "Follow-up").click();
  await runa.page.clock.fastForward("00:21");
  await expect(held(runa.page).getByRole("listitem").filter({ hasText: "Vigga Writer" })).toContainText("has the step “Follow-up” since");
  const theirs = form(runa.page).getByRole("textbox", { name: "What to do next" });
  await expect(theirs).toHaveValue("Replace the disk in rack B");
  await expect(theirs).toBeDisabled();
  await expect(form(runa.page).getByText("Vigga Writer has this step checked out")).toBeVisible();

  // She may see the secret she kept, after confirming it's her: for a moment only.
  await stepButton(runa.page, "Visit").click();
  await password.getByRole("button", { name: "Show for 30 seconds" }).click();
  const stepUp = runa.page.getByRole("dialog", { name: "Confirm it's you" });
  await expect(stepUp).toContainText("before it shows a secret");
  await stepUp.getByLabel("Code from your authenticator app").fill(totp(runa.secret, 1));
  await stepUp.getByRole("button", { name: "Verify code" }).click();
  const shown = password.getByRole("textbox", { name: "Console password, shown for a moment" });
  await expect(shown).toHaveValue(SECRET);
  await expect(password.getByText(/Hidden again in \d+ seconds?\./)).toBeVisible();
  await password.getByRole("button", { name: "Hide it now" }).click();
  await expect(shown).toHaveCount(0);
  expect(await runa.page.content()).not.toContain(SECRET);

  // An Administrator ends her checkout, after being told what that does. The preview
  // of someone who may read styles has one to pick.
  await admin.page.goto(reportUrl);
  await expect(preview(admin.page).getByText("Preview in")).toBeVisible();
  await held(admin.page).getByRole("listitem").filter({ hasText: "Runa Reporter" }).getByRole("button", { name: "End it" }).click();
  const ending = admin.page.getByRole("dialog", { name: "End Runa Reporter's checkout" });
  await expect(ending).toContainText("Runa Reporter is told by email");
  await shot(admin.page, "5-end-checkout");
  await ending.getByRole("button", { name: "End the checkout" }).click();
  await expect(toastWith(admin.page, "Runa Reporter's checkout is ended.")).toBeVisible();
  await expect(held(admin.page).getByRole("listitem").filter({ hasText: "Runa Reporter" })).toHaveCount(0);

  // Her page finds out at its next look: the step is read-only again, and free to take.
  await runa.page.clock.fastForward("00:21");
  await expect(form(runa.page).getByRole("button", { name: "Check out this step" })).toBeVisible();
  await expect(checked).toBeDisabled();

  // The second technician releases her step when she's done.
  await held(vigga.page).getByRole("listitem").filter({ hasText: "You have" }).getByRole("button", { name: "Release" }).click();
  await expect(held(vigga.page)).toContainText("Nobody has this report checked out.");
  await expect(form(vigga.page).getByRole("textbox", { name: "What to do next" })).toBeDisabled();

  // The Administrator discards the draft, with its number typed to confirm.
  await admin.page.getByRole("button", { name: "Discard", exact: true }).click();
  const discarding = admin.page.getByRole("dialog", { name: `Discard ${number}` });
  const forGood = discarding.getByRole("button", { name: "Discard for good" });
  await expect(forGood).toBeDisabled();
  await discarding.getByLabel("Type the report's number to confirm").fill(number);
  await forGood.click();
  await expect(toastWith(admin.page, `${number} is discarded.`)).toBeVisible();
  await expect(admin.page).toHaveURL(new RegExp(`/projects/${project.id}$`));
  await expect(admin.page.getByRole("region", { name: "Reports" }).getByText("No reports yet.")).toBeVisible();

  // A page that still had it open says so at its next look.
  await expect(vigga.page.getByRole("main").getByText("That report doesn't exist.")).toBeVisible({ timeout: 30_000 });

  expect(refused.filter((url) => url.includes("/api/styles"))).toEqual([]);
  expect(violations).toEqual([]);
  await admin.context.close();
  await runa.context.close();
  await vigga.context.close();
});
