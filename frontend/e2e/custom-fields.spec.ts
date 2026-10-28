import { expect, test, type Browser, type Page } from "@playwright/test";
import { setUpAuthenticatorApp, signIn, toastWith, watchForCspViolations } from "./helpers";

const CUSTOMER = "Kystlys Energi A/S";

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/custom-fields-${name}.png`, fullPage: true });
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

test("a custom field is defined, filled in on a customer, and read by templates", async ({ browser }) => {
  // A designer defines it.
  const designer = await signedIn(browser, "e2e-fielder");
  const violations = watchForCspViolations(designer.page);
  await menu(designer.page, "Custom fields").click();
  await designer.page.getByRole("button", { name: "Add a field", exact: true }).click();
  const dialog = designer.page.getByRole("dialog", { name: "Add a field" });
  await dialog.getByLabel("Label").fill("Support agreement");
  await expect(dialog.getByLabel("Name in templates")).toHaveValue("support_agreement");
  await dialog.getByLabel("Type").selectOption({ label: "Dropdown" });
  await dialog.getByLabel("Options").fill("Gold\nSilver");
  await dialog.getByRole("button", { name: "Add the field" }).click();
  await expect(toastWith(designer.page, "customer.custom.support_agreement")).toBeVisible();
  await expect(designer.page.getByRole("row", { name: /Support agreement customer\.custom\.support_agreement Dropdown: Gold, Silver/ })).toBeVisible();
  await shot(designer.page, "1-definitions");

  // A manager fills it in on a new customer.
  const manager = await signedIn(browser, "e2e-filler");
  await menu(manager.page, "All customers").click();
  await manager.page.getByRole("link", { name: "Add customer" }).click();
  await manager.page.getByLabel("Name", { exact: true }).fill(CUSTOMER);
  await manager.page.getByLabel(/^Support agreement/).selectOption("Gold");
  await manager.page.getByRole("button", { name: "Add customer" }).click();
  await expect(manager.page.getByRole("heading", { name: CUSTOMER })).toBeVisible();
  const facts = manager.page.locator("dl.facts");
  await expect(facts.getByText("Support agreement")).toBeVisible();
  await expect(facts.getByText("Gold", { exact: true })).toBeVisible();
  await menu(manager.page, "Customer settings").click();
  await manager.page.getByLabel(/^Support agreement/).selectOption("Silver");
  await manager.page.getByRole("button", { name: "Save details" }).click();
  await expect(toastWith(manager.page, "Details saved.")).toBeVisible();
  await manager.context.close();

  // Templates read it, and the Data tab lists it with an example.
  await menu(designer.page, "Templates").click();
  await designer.page.getByRole("button", { name: "New template" }).click();
  await designer.page.getByRole("dialog").getByLabel("Name", { exact: true }).fill("Service visit");
  await designer.page.getByRole("dialog").getByRole("button", { name: "Create" }).click();
  await designer.page.getByRole("link", { name: "Data" }).click();
  await expect(designer.page.getByRole("row", { name: /customer\.custom\.support_agreement Support agreement text "Gold"/ })).toBeVisible();
  await designer.page.getByRole("textbox", { name: "Expression" }).fill('customer.custom.support_agreement == "Gold"');
  await expect(designer.page.getByRole("status")).toHaveText("true, which is yes or no");
  await shot(designer.page, "2-data");

  expect(violations).toEqual([]);
  await designer.context.close();
});
