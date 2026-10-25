import { expect, test, type Browser, type Page } from "@playwright/test";
import { setUpAuthenticatorApp, signIn, toastWith, totp, watchForCspViolations } from "./helpers";

const CUSTOMER = "Fjordlys Energi A/S";
const PROJECT = "Ransomware incident";

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/customers-${name}.png`, fullPage: true });
}

/** A link in the side menu; a string matches the whole name, a pattern its start (counts follow). */
function menu(page: Page, name: string | RegExp) {
  return page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name, exact: typeof name === "string" });
}

/** Someone signed in, in a browser of their own, with an authenticator app set up. */
async function signedIn(browser: Browser, username: string, options: { clock?: boolean } = {}) {
  const context = await browser.newContext();
  // A clock the test can move on, for what the app checks once a minute.
  if (options.clock) await context.clock.install();
  const page = await context.newPage();
  await signIn(page, username);
  const secret = await setUpAuthenticatorApp(page);
  return { context, page, secret };
}

async function pickCustomer(page: Page) {
  await page.getByRole("button", { name: "Customer Choose a customer" }).click();
  await page.getByRole("dialog", { name: "Choose a customer" }).getByLabel("Search customers").fill("fjord");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: CUSTOMER })).toBeVisible();
}

test("customers and projects, from adding one to deleting it", async ({ browser }) => {
  const { context: bossContext, page: boss, secret: bossSecret } = await signedIn(browser, "e2e-boss");
  const violations = watchForCspViolations(boss);

  // An administrator adds the customer; it opens in the side menu.
  await menu(boss, "All customers").click();
  await expect(boss.getByRole("main").getByText("No customers yet.")).toBeVisible();
  await boss.getByRole("link", { name: "Add customer" }).click();
  await boss.getByLabel("Name").fill(CUSTOMER);
  await boss.getByLabel("CVR number (optional)").fill("1234 5678");
  await boss.getByLabel("Address").fill("Havnegade 4\n8000 Aarhus C");
  await boss.getByRole("button", { name: "Add customer" }).click();
  await expect(toastWith(boss, "with its own encryption key")).toBeVisible();
  await expect(boss.getByRole("heading", { name: CUSTOMER })).toBeVisible();
  await expect(boss.getByText("12 34 56 78")).toBeVisible();
  await expect(boss.getByRole("button", { name: `Customer ${CUSTOMER}` })).toBeVisible();
  await expect(menu(boss, "Overview")).toHaveAttribute("aria-current", "page");

  // Its sites and contacts, then who works with it: a technician and a reviewer.
  await menu(boss, "Contacts & sites").click();
  await boss.getByRole("button", { name: "Add site" }).click();
  await boss.getByRole("dialog").getByLabel("Name").fill("Hovedkontor");
  await boss.getByRole("dialog").getByLabel("Address").fill("Havnegade 4");
  await boss.getByRole("button", { name: "Save site" }).click();
  await boss.getByRole("button", { name: "Add contact" }).click();
  const contact = boss.getByRole("dialog");
  await contact.getByLabel("Name").fill("Sigrid Holm");
  await contact.getByLabel("Role").fill("IT manager");
  await contact.getByLabel("Email").fill("sigrid@fjordlys.example");
  await contact.getByRole("button", { name: "Save contact" }).click();
  await expect(boss.getByText("sigrid@fjordlys.example")).toBeVisible();
  await shot(boss, "1-contacts");

  await menu(boss, "People").click();
  await boss.getByRole("checkbox", { name: /Tor Tekniker/ }).check();
  await boss.getByRole("checkbox", { name: /Rikke Reviewer/ }).check();
  await boss.getByRole("button", { name: "Save", exact: true }).click();
  await expect(toastWith(boss, "Who works with this customer is saved.")).toBeVisible();
  await menu(boss, "Overview").click();
  await expect(boss.getByRole("region", { name: "People on this customer" })).toContainText("Tor Tekniker");

  // A Manager starts a project and chooses who writes and who reviews it.
  const { context: managerContext, page: manager } = await signedIn(browser, "e2e-manager");
  await pickCustomer(manager);
  await expect(menu(manager, "Customer settings")).toBeVisible();
  await manager.getByRole("main").getByRole("link", { name: "New project" }).click();
  await manager.getByLabel("Name").fill(PROJECT);
  await manager.getByLabel("Start date").fill("2026-10-20");
  await manager.getByLabel("Responsible technician").selectOption({ label: "Tor Tekniker" });
  await manager.getByLabel("Reviewer").selectOption({ label: "Rikke Reviewer" });
  await manager.getByLabel("Customer contact").selectOption({ label: "Sigrid Holm, IT manager" });
  await manager.getByRole("checkbox", { name: "Hovedkontor" }).check();
  await manager.getByRole("radio", { name: /TLP:RED/ }).check();
  await shot(manager, "2-new-project");
  await manager.getByRole("button", { name: "Create project" }).click();
  await expect(manager.getByText(/^P-\d{4}-0001$/)).toBeVisible();
  await expect(manager.locator(".tags").getByText("TLP:RED")).toBeVisible();
  await expect(menu(manager, /^Projects/)).toContainText("1");
  await expect(menu(manager, "Reports")).toHaveAttribute("aria-current", "page");
  await shot(manager, "3-project");

  // The team: the responsible technician and the reviewer are on it and stay on it.
  await menu(manager, "Team").click();
  for (const name of [/Tor Tekniker/, /Rikke Reviewer/]) {
    const member = manager.getByRole("checkbox", { name });
    await expect(member).toBeChecked();
    await expect(member).toBeDisabled();
  }

  // The technician works in it, but can't change or archive it.
  const { context: techContext, page: tech } = await signedIn(browser, "e2e-tech", { clock: true });
  await expect(tech.getByRole("heading", { name: "Your projects" })).toBeVisible();
  await tech.getByRole("main").getByRole("link", { name: PROJECT }).click();
  await expect(tech.getByRole("heading", { name: PROJECT })).toBeVisible();
  await expect(tech.getByRole("button", { name: "Archive project" })).toHaveCount(0);
  await menu(tech, "Details").click();
  await expect(tech.getByText("Rikke Reviewer")).toBeVisible();
  await expect(tech.getByRole("button", { name: "Save project" })).toHaveCount(0);
  await expect(menu(tech, "Customer settings")).toHaveCount(0);

  // Unassigned, the technician loses the customer at the next check, without
  // signing in again.
  await menu(boss, "People").click();
  await boss.getByRole("checkbox", { name: /Tor Tekniker/ }).uncheck();
  await boss.getByRole("button", { name: "Save", exact: true }).click();
  await expect(toastWith(boss, "Who works with this customer is saved.")).toBeVisible();
  await tech.clock.fastForward("01:05");
  await expect(toastWith(tech, `You no longer have access to ${PROJECT}.`)).toBeVisible();
  await expect(tech).toHaveURL(/\/customers$/);
  await expect(tech.getByRole("main").getByText("No customers yet.")).toBeVisible();
  await expect(tech.getByRole("button", { name: "Customer Choose a customer" })).toBeVisible();

  // The Manager archives it; deleting the customer is for an Administrator only.
  await menu(manager, "Reports").click();
  await manager.getByRole("button", { name: "Archive project" }).click();
  await manager.getByRole("dialog").getByRole("button", { name: "Archive project" }).click();
  await expect(manager.getByText(/The project and its reports are read-only/)).toBeVisible();
  await expect(menu(manager, /^Archived/)).toContainText("1");
  await menu(manager, "Details").click();
  await expect(manager.getByRole("button", { name: "Save project" })).toHaveCount(0);
  await menu(manager, "Customer settings").click();
  await expect(manager.getByRole("heading", { name: "Details" })).toBeVisible();
  await expect(manager.getByRole("button", { name: "Delete customer" })).toHaveCount(0);

  // Deleting the customer asks to confirm it's you, then takes everything with it.
  await boss.reload();
  await menu(boss, /^Archived/).click();
  await expect(boss.getByRole("main").getByRole("link", { name: PROJECT })).toBeVisible();
  await menu(boss, "Customer settings").click();
  await boss.getByRole("button", { name: "Delete customer" }).click();
  const confirm = boss.getByRole("dialog", { name: `Delete ${CUSTOMER}` });
  const forGood = confirm.getByRole("button", { name: "Delete for good" });
  await expect(forGood).toBeDisabled();
  await confirm.getByLabel("Type the customer's name to confirm").fill(CUSTOMER);
  await shot(boss, "4-delete");
  await forGood.click();
  const stepUp = boss.getByRole("dialog", { name: "Confirm it's you" });
  await stepUp.getByLabel("Code from your authenticator app").fill(totp(bossSecret, 1));
  await stepUp.getByRole("button", { name: "Verify code" }).click();
  await expect(toastWith(boss, "is deleted, and its key with it")).toBeVisible();
  await expect(boss.getByRole("main").getByText("No customers yet.")).toBeVisible();
  await expect(boss.getByRole("button", { name: "Customer Choose a customer" })).toBeVisible();
  await expect(toastWith(boss, "You no longer have access")).toHaveCount(0);

  expect(violations).toEqual([]);
  await bossContext.close();
  await managerContext.close();
  await techContext.close();
});
