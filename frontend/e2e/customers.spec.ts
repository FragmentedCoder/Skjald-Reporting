import { expect, test, type Page } from "@playwright/test";
import { setUpAuthenticatorApp, signIn, toastWith, totp, watchForCspViolations } from "./helpers";

const CUSTOMER = "Fjordlys Energi A/S";

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/customers-${name}.png`, fullPage: true });
}

test("customers and projects, from adding one to deleting it", async ({ browser }) => {
  const bossContext = await browser.newContext();
  const boss = await bossContext.newPage();
  const violations = watchForCspViolations(boss);
  await signIn(boss, "e2e-boss");
  const bossSecret = await setUpAuthenticatorApp(boss);

  // An administrator adds the customer, a site and a contact, and assigns a technician.
  await boss.getByRole("link", { name: "Customers", exact: true }).click();
  await expect(boss.getByText("No customers yet.")).toBeVisible();
  await boss.getByRole("link", { name: "Add customer" }).click();
  await boss.getByLabel("Name").fill(CUSTOMER);
  await boss.getByLabel("CVR number (optional)").fill("1234 5678");
  await boss.getByLabel("Address").fill("Havnegade 4\n8000 Aarhus C");
  await boss.getByRole("button", { name: "Add customer" }).click();
  await expect(toastWith(boss, "with its own encryption key")).toBeVisible();
  await expect(boss.getByRole("heading", { name: CUSTOMER })).toBeVisible();
  await expect(boss.getByText("12 34 56 78")).toBeVisible();

  await boss.getByRole("tab", { name: "Details" }).click();
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
  await shot(boss, "1-details");

  await boss.getByRole("tab", { name: /People/ }).click();
  await boss.getByRole("checkbox", { name: /Tor Tekniker/ }).check();
  await boss.getByRole("button", { name: "Save", exact: true }).click();
  await expect(boss.getByRole("tab", { name: "People (1)" })).toBeVisible();

  // The technician sees the customer and starts a project for it.
  const techContext = await browser.newContext();
  const tech = await techContext.newPage();
  await signIn(tech, "e2e-tech");
  await setUpAuthenticatorApp(tech);
  await expect(tech.getByText("Start a project from one of")).toBeVisible();
  await tech.getByRole("link", { name: "Customers", exact: true }).click();
  await tech.getByRole("link", { name: CUSTOMER }).click();
  await tech.getByRole("link", { name: "New project" }).click();
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
  await shot(tech, "3-project");

  // Home lists it as theirs; archiving makes it read-only.
  await tech.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Home" }).click();
  await expect(tech.getByRole("heading", { name: "Your projects" })).toBeVisible();
  await tech.getByRole("link", { name: "Ransomware incident" }).click();
  await tech.getByRole("button", { name: "Archive project" }).click();
  await tech.getByRole("dialog").getByRole("button", { name: "Archive project" }).click();
  await expect(tech.getByText(/The project and its reports are read-only/)).toBeVisible();
  await expect(tech.getByRole("button", { name: "Save project" })).toHaveCount(0);

  // Deleting the customer asks to confirm it's you, then takes everything with it.
  await boss.reload();
  await boss.getByRole("tab", { name: "Archived (1)" }).click();
  await expect(boss.getByRole("link", { name: "Ransomware incident" })).toBeVisible();
  await boss.getByRole("tab", { name: "Details" }).click();
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
  await expect(boss.getByText("No customers yet.")).toBeVisible();

  await tech.reload();
  await expect(tech.getByText("That project doesn't exist.")).toBeVisible();

  expect(violations).toEqual([]);
  await bossContext.close();
  await techContext.close();
});
