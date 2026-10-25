import { expect, test, type Page } from "@playwright/test";
import { setUpAuthenticatorApp, signIn, toastWith, totp, watchForCspViolations } from "./helpers";

const CUSTOMER = "Fjordlys Energi A/S";

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/customers-${name}.png`, fullPage: true });
}

/** A link in the side menu; a string matches the whole name, a pattern its start (counts follow). */
function menu(page: Page, name: string | RegExp) {
  return page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name, exact: typeof name === "string" });
}

test("customers and projects, from adding one to deleting it", async ({ browser }) => {
  const bossContext = await browser.newContext();
  const boss = await bossContext.newPage();
  const violations = watchForCspViolations(boss);
  await signIn(boss, "e2e-boss");
  const bossSecret = await setUpAuthenticatorApp(boss);

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

  // Its sites and contacts, then who works with it.
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
  await boss.getByRole("button", { name: "Save", exact: true }).click();
  await expect(toastWith(boss, "Who works with this customer is saved.")).toBeVisible();
  await menu(boss, "Overview").click();
  await expect(boss.getByRole("region", { name: "People on this customer" })).toContainText("Tor Tekniker");

  // The technician picks the customer in the side menu and starts a project for it.
  const techContext = await browser.newContext();
  const tech = await techContext.newPage();
  await signIn(tech, "e2e-tech");
  await setUpAuthenticatorApp(tech);
  await expect(tech.getByText("Start a project from one of")).toBeVisible();
  await tech.getByRole("button", { name: "Customer Choose a customer" }).click();
  await tech.getByRole("dialog", { name: "Choose a customer" }).getByLabel("Search customers").fill("fjord");
  await tech.keyboard.press("Enter");
  await expect(tech.getByRole("heading", { name: CUSTOMER })).toBeVisible();
  await expect(menu(tech, "Customer settings")).toHaveCount(0);
  await tech.getByRole("main").getByRole("link", { name: "New project" }).click();
  await tech.getByLabel("Name").fill("Ransomware incident");
  await tech.getByLabel("Start date").fill("2026-10-20");
  await expect(tech.getByLabel("Responsible technician")).toHaveValue(/\d+/);
  await tech.getByLabel("Customer contact").selectOption({ label: "Sigrid Holm, IT manager" });
  await tech.getByRole("checkbox", { name: "Hovedkontor" }).check();
  await tech.getByRole("radio", { name: /TLP:RED/ }).check();
  await shot(tech, "2-new-project");
  await tech.getByRole("button", { name: "Create project" }).click();
  await expect(tech.getByText(/^P-\d{4}-0001$/)).toBeVisible();
  await expect(tech.locator(".tags").getByText("TLP:RED")).toBeVisible();
  await expect(menu(tech, /^Projects/)).toContainText("1");
  await expect(menu(tech, "Reports")).toHaveAttribute("aria-current", "page");
  await shot(tech, "3-project");

  // The team: its responsible technician is on it and stays on it.
  await menu(tech, "Team").click();
  const responsible = tech.getByRole("checkbox", { name: /Tor Tekniker/ });
  await expect(responsible).toBeChecked();
  await expect(responsible).toBeDisabled();
  await menu(tech, "Details").click();
  await expect(tech.getByRole("button", { name: "Save project" })).toBeVisible();

  // Home lists it as theirs; archiving makes it read-only, and it moves to Archived.
  await menu(tech, "Home").click();
  await expect(tech.getByRole("heading", { name: "Your projects" })).toBeVisible();
  await tech.getByRole("main").getByRole("link", { name: "Ransomware incident" }).click();
  await tech.getByRole("button", { name: "Archive project" }).click();
  await tech.getByRole("dialog").getByRole("button", { name: "Archive project" }).click();
  await expect(tech.getByText(/The project and its reports are read-only/)).toBeVisible();
  await expect(menu(tech, /^Archived/)).toContainText("1");
  await menu(tech, "Details").click();
  await expect(tech.getByRole("button", { name: "Save project" })).toHaveCount(0);

  // Deleting the customer asks to confirm it's you, then takes everything with it.
  await boss.reload();
  await menu(boss, /^Archived/).click();
  await expect(boss.getByRole("main").getByRole("link", { name: "Ransomware incident" })).toBeVisible();
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

  await tech.reload();
  await expect(tech.getByText("That project doesn't exist.")).toBeVisible();

  expect(violations).toEqual([]);
  await bossContext.close();
  await techContext.close();
});
