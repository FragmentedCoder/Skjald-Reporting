import { expect, test, type Browser, type Page } from "@playwright/test";
import { dismissToasts, setUpAuthenticatorApp, signIn, toastWith, watchForCspViolations } from "./helpers";

const CUSTOMER = "Havbris Shipping A/S";

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `e2e-results/screens/styles-${name}.png`, fullPage: true });
}

function menu(page: Page, name: string | RegExp) {
  return page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: typeof name === "string" });
}

async function signedIn(browser: Browser, username: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, username);
  await setUpAuthenticatorApp(page);
  return { context, page };
}

/** A one-page A4 PDF with a blue band across the top: a stand-in for a letterhead. */
function letterhead(): Buffer {
  const stream = "0.17 0.36 0.54 rg 0 782 595.28 60 re f";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] /Contents 4 0 R >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) out += `${String(offset).padStart(10, "0")} 00000 n \n`;
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

test("a designer makes a company style and designs its pages", async ({ browser }) => {
  const { context, page } = await signedIn(browser, "e2e-stylist");
  const violations = watchForCspViolations(page);

  await menu(page, "Styles").click();
  await expect(page.getByRole("heading", { name: "Styles" })).toBeVisible();
  await page.getByRole("button", { name: "New style" }).click();
  const dialog = page.getByRole("dialog", { name: "New style" });
  await dialog.getByLabel("Name").fill("Nordlys brand");
  await dialog.getByRole("button", { name: "Make the style" }).click();
  await expect(page.getByRole("heading", { name: "Nordlys brand" })).toBeVisible();

  // Colours: one set here, and a pale one that the contrast check catches.
  const headings = page.getByRole("textbox", { name: "Headings", exact: true });
  await headings.fill("#1D3A5F");
  await headings.press("Tab");
  const muted = page.getByRole("textbox", { name: "Muted text", exact: true });
  await muted.fill("#BBBBBB");
  await muted.press("Tab");
  await expect(page.getByRole("status").filter({ hasText: "won't read well" })).toContainText("Muted text");
  await page.locator(".colour").filter({ has: muted }).getByRole("button", { name: "Use the one below" }).click();
  await expect(page.getByText("won't read well")).toHaveCount(0);

  // The sample report is drawn in the style.
  const preview = page.getByRole("region", { name: "The sample report in this style" });
  await expect(preview.locator(".section-heading").first()).toHaveCSS("color", "rgb(29, 58, 95)");

  // The other pages' design: a line of text with a variable, moved with the keyboard.
  await page.getByRole("button", { name: "Page designs" }).click();
  await page.getByRole("button", { name: "Other pages" }).click();
  await page.getByRole("button", { name: "Design this page here" }).click();
  await page.getByRole("group", { name: "Add an element" }).getByRole("button", { name: "Text" }).click();
  await page.getByLabel("Text", { exact: true }).fill("{{ customer.name }} · Confidential");
  const element = page.getByRole("button", { name: /^Text “\{\{ customer\.name \}\} · Confidential”/ });
  await element.focus();
  for (let i = 0; i < 5; i++) await element.press("ArrowRight");
  await expect(page.getByLabel("From the left (mm)")).toHaveValue("23");
  await shot(page, "1-designer");

  // An expression the style can't print is refused when saving.
  await page.getByLabel("Text", { exact: true }).fill("{{ answers.cvss }}");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Element 5 on the other pages");
  await page.getByLabel("Text", { exact: true }).fill("{{ customer.name }} · Confidential");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(toastWith(page, "Style saved.")).toBeVisible();
  await expect(page.getByText(/version 2, saved by Sigrun Stylist/)).toBeVisible();

  await page.getByRole("button", { name: "Colours and type" }).click();
  await expect(preview.getByText("Fjordvik Logistik A/S · Confidential").first()).toBeVisible();
  await shot(page, "2-preview");

  // It becomes the company's default.
  await page.getByRole("link", { name: "Styles" }).first().click();
  await page.getByRole("button", { name: "Actions for Nordlys brand" }).click();
  await page.getByRole("menuitem", { name: "Make the company default" }).click();
  await expect(page.getByRole("row", { name: /Nordlys brand/ }).getByText("Company default")).toBeVisible();

  expect(violations).toEqual([]);
  await context.close();
});

test("a manager gives a customer a report background, converted with no network", async ({ browser }) => {
  const { context, page } = await signedIn(browser, "e2e-brandkeeper");
  const violations = watchForCspViolations(page);

  await menu(page, "All customers").click();
  await page.getByRole("link", { name: "Add customer" }).click();
  await page.getByLabel("Name").fill(CUSTOMER);
  await page.getByLabel("Address").fill("Kajen 2\n6700 Esbjerg");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByRole("heading", { name: CUSTOMER })).toBeVisible();
  await menu(page, "Customer settings").click();

  // The letterhead goes to the renderer, which has no network, and comes back as SVG.
  await page.getByLabel("Upload a background").setInputFiles({ name: "letterhead.pdf", mimeType: "application/pdf", buffer: letterhead() });
  const page1 = page.getByRole("img", { name: "Page 1 of the report background" });
  await expect(page1).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Behind every page")).toBeVisible();
  await expect(page1).toHaveJSProperty("complete", true);
  expect(await page1.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);

  await page.getByLabel("Top", { exact: true }).fill("45");
  await page.getByRole("button", { name: "Save margins" }).click();
  await expect(toastWith(page, "Margins saved.")).toBeVisible();

  // A file that isn't A4 is refused with the reason.
  await dismissToasts(page);
  await page.getByLabel("Replace the background").setInputFiles({ name: "wide.svg", mimeType: "image/svg+xml",
    buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100"><rect width="400" height="20"/></svg>') });
  await expect(toastWith(page, "A4 page's proportions")).toBeVisible();

  // The styles its reports use: the company's default to start with.
  await expect(page.getByLabel("Reports start in")).toContainText("The company default (Nordlys brand)");
  await page.getByLabel("Reports start in").selectOption({ label: "Nordlys brand" });
  await page.getByRole("button", { name: "Save report styles" }).click();
  await expect(toastWith(page, "Report styles saved.")).toBeVisible();
  await shot(page, "3-customer");

  expect(violations).toEqual([]);
  await context.close();
});
