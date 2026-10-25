import { expect, test, type Page } from "@playwright/test";
import { setUpAuthenticatorApp, signIn, watchForCspViolations } from "./helpers";

// The side menu with a few (fictional) customers and their projects, as an
// administrator and as a technician on some of them. A TLP:RED project is listed
// only for administrators and its own team. Screenshots go to e2e-results/screens.

interface Created {
  id: number;
}

interface Detail extends Created {
  assignable: { id: number; username: string }[];
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

async function addCustomer(page: Page, name: string, cvr: string, contacts: string[][], sites: string[]) {
  const customer = await call<Detail>(page, "POST", "/customers", { name, cvr, address: "Havnegade 4\n8000 Aarhus C" });
  for (const [contact, role, email] of contacts) {
    await call(page, "POST", `/customers/${customer.id}/contacts`, { name: contact, role, email });
  }
  for (const site of sites) await call(page, "POST", `/customers/${customer.id}/sites`, { name: site });
  return customer;
}

function menu(page: Page) {
  return page.getByRole("navigation", { name: "Main" });
}

test("the side menu, with customers and projects", async ({ browser }) => {
  const shotsOf = (page: Page, theme: string) => (name: string) =>
    page.screenshot({ path: `e2e-results/screens/menu-${name}-${theme}.png` });

  const metteContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const mette = await metteContext.newPage();
  const violations = watchForCspViolations(mette);
  await signIn(mette, "e2e-mette");
  await setUpAuthenticatorApp(mette);

  const fjordlys = await addCustomer(mette, "Fjordlys Energi A/S", "12345678",
    [["Sigrid Holm", "IT manager", "sigrid@fjordlys.example"], ["Anders Vang", "CISO", "anders@fjordlys.example"]],
    ["Hovedkontor", "Datacenter Aarhus"]);
  const nordhavn = await addCustomer(mette, "Nordhavn Logistik ApS", "87654321",
    [["Lise Kjær", "Head of IT", "lise@nordhavn.example"]], ["Lager Køge"]);
  await addCustomer(mette, "Sølvbjerg Kommune", "29189900", [], []);
  const bob = fjordlys.assignable.find((p) => p.username === "e2e-bob")!.id;
  for (const customer of [fjordlys, nordhavn]) {
    await call(mette, "PUT", `/customers/${customer.id}/assignments`, { user_ids: [bob] });
  }

  const project = (customer: Created, name: string, classification: string, responsible: number | null) =>
    call<Created>(mette, "POST", `/customers/${customer.id}/projects`,
      { name, classification, responsible_id: responsible, start_date: "2026-10-01" });
  const ransomware = await project(fjordlys, "Ransomware incident", "TLP:RED", bob);
  await project(fjordlys, "Annual penetration test", "TLP:AMBER", null);
  await project(fjordlys, "Firewall review", "TLP:CLEAR", bob);
  await project(fjordlys, "Insider investigation", "TLP:RED", null);
  const phishing = await project(fjordlys, "Phishing exercise 2025", "TLP:GREEN", null);
  await call(mette, "POST", `/projects/${phishing.id}/archive`);
  await project(nordhavn, "Network segmentation", "TLP:AMBER+STRICT", bob);

  // The administrator: the customer picked in the menu, its sections and projects.
  for (const theme of ["light", "dark"] as const) {
    await mette.emulateMedia({ colorScheme: theme });
    const shot = shotsOf(mette, theme);
    await mette.goto(`/customers/${fjordlys.id}`);
    await expect(mette.getByRole("heading", { name: "Fjordlys Energi A/S" })).toBeVisible();
    await expect(menu(mette).getByRole("link", { name: /^Insider investigation/ })).toBeVisible();
    await shot("1-customer");

    await menu(mette).getByRole("button", { name: /^Customer/ }).click();
    await expect(mette.getByRole("dialog", { name: "Choose a customer" })).toBeVisible();
    await shot("2-picker");
    await mette.keyboard.press("Escape");

    await mette.goto(`/projects/${ransomware.id}/team`);
    await expect(mette.getByRole("checkbox", { name: /Bob Bager/ })).toBeChecked();
    await shot("3-project-team");

    await mette.goto(`/projects/${phishing.id}`);
    await expect(menu(mette).getByRole("link", { name: "Reports" })).toBeVisible();
    await shot("4-archived-project");
  }

  // At phone width the menu slides in over the page.
  // Without the slide, so the screenshot shows the menu fully open.
  await mette.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await mette.setViewportSize({ width: 390, height: 844 });
  await mette.goto(`/customers/${fjordlys.id}/projects`);
  await mette.getByRole("button", { name: "Open the menu" }).click();
  await expect(menu(mette).getByRole("link", { name: "Overview" })).toBeVisible();
  await shotsOf(mette, "light")("5-phone");
  await mette.keyboard.press("Escape");
  await expect(menu(mette).getByRole("link", { name: "Overview" })).toBeHidden();

  // Bob, a technician on both customers: he sees his TLP:RED project and the
  // others, but not the TLP:RED one he isn't on, nor the customer he isn't on.
  const bobContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const bobPage = await bobContext.newPage();
  await signIn(bobPage, "e2e-bob");
  await setUpAuthenticatorApp(bobPage);
  await bobPage.goto(`/customers/${fjordlys.id}`);
  await expect(menu(bobPage).getByRole("link", { name: /^Ransomware incident/ })).toBeVisible();
  await expect(menu(bobPage).getByRole("link", { name: /^Firewall review/ })).toBeVisible();
  await expect(menu(bobPage).getByRole("link", { name: /^Annual penetration test/ })).toBeVisible();
  await expect(menu(bobPage).getByRole("link", { name: /^Insider investigation/ })).toHaveCount(0);
  await expect(menu(bobPage).getByRole("link", { name: /^Projects/ })).toContainText("3");
  await shotsOf(bobPage, "light")("6-technician");
  await menu(bobPage).getByRole("button", { name: /^Customer/ }).click();
  const picker = bobPage.getByRole("dialog", { name: "Choose a customer" });
  await expect(picker.getByRole("button")).toHaveCount(2);
  await expect(picker).not.toContainText("Sølvbjerg");

  expect(violations).toEqual([]);
  await metteContext.close();
  await bobContext.close();
});
