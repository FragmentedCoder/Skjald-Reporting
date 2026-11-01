// The report's details as they stand now, for the Database page's examples: the
// company's name, your own profile as the author, and the customer open in the side
// menu with its open (or newest) project, that project's contact and first site.
// Only what the person may already see; what isn't there yet (a report's own
// details, a reviewer, a detail left empty) keeps its made-up example.

import { api } from "#lib/api.js";
import type { Profile } from "#lib/admin.js";
import { branding, loadBranding } from "#lib/branding.svelte.js";
import type { CustomerDetail, ProjectDetail } from "#lib/customers.js";
import { openCustomer, workspace } from "#lib/workspace.svelte.js";

export interface Current {
  /** Values by name, such as "customer.name" or "customer.custom.agreement". */
  values: Record<string, unknown>;
  /** Where they're from, for people to read. */
  sources: string[];
}

const PROFILE: (keyof Profile)[] = ["display_name", "first_name", "middle_name", "last_name", "job_title", "department", "company", "email", "phone"];

/** A project's date as expressions read it: midnight where the browser is. */
function day(date: string | null): Date | null {
  return date ? new Date(`${date}T00:00`) : null;
}

function custom(values: Record<string, unknown>, root: "customer" | "project", found: Record<string, unknown> | null) {
  for (const [key, value] of Object.entries(found ?? {})) values[`${root}.custom.${key}`] = value;
}

/** What's known now, fetched with the person's own access. */
export async function currentValues(): Promise<Current> {
  const values: Record<string, unknown> = {};
  const sources: string[] = [];
  await loadBranding();
  if (branding.current.company_name) {
    values["company.name"] = branding.current.company_name;
    sources.push("the company's settings");
  }
  const me = await api<Profile>("GET", "/account").catch(() => null);
  if (me) {
    for (const key of PROFILE) values[`author.${key}`] = me[key];
    sources.push("your profile (as the author)");
  }
  const open = openCustomer();
  const customer = open?.visibility === "full" ? await api<CustomerDetail>("GET", `/customers/${open.id}`).catch(() => null) : null;
  if (customer) {
    Object.assign(values, { "customer.name": customer.name, "customer.cvr": customer.cvr, "customer.address": customer.address, "customer.language": customer.language });
    custom(values, "customer", customer.custom);
    const picked = workspace.project ?? workspace.projects?.[0] ?? null;
    const project = picked ? await api<ProjectDetail>("GET", `/projects/${picked.id}`).catch(() => null) : null;
    if (project) {
      Object.assign(values, {
        "project.name": project.name, "project.number": project.number, "project.classification": project.classification,
        "project.start_date": day(project.start_date), "project.end_date": day(project.end_date),
      });
      custom(values, "project", project.custom);
      const contact = customer.contacts?.find((c) => c.id === project.contact?.id);
      if (contact) Object.assign(values, { "contact.name": contact.name, "contact.role": contact.role, "contact.email": contact.email, "contact.phone": contact.phone });
      const site = customer.sites?.find((s) => s.id === project.sites[0]?.id);
      if (site) Object.assign(values, { "site.name": site.name, "site.address": site.address });
    }
    sources.push(`${customer.name}${project ? ` and its project ${project.number}` : ""} (open in the side menu)`);
  }
  return { values, sources };
}

/**
 * The sample context with what's known now in its place: each name with a value of
 * its own (not empty) replaces the example and is listed in `live`.
 */
export function withCurrent(sample: Record<string, Record<string, unknown>>, current: Record<string, unknown>): { values: Record<string, Record<string, unknown>>; live: Set<string> } {
  const values = Object.fromEntries(Object.entries(sample).map(([root, group]) => [root, { ...group, ...(group.custom ? { custom: { ...(group.custom as object) } } : {}) }]));
  const live = new Set<string>();
  for (const [name, value] of Object.entries(current)) {
    if (value === null || value === undefined || value === "") continue;
    const parts = name.split(".");
    let at: Record<string, unknown> = values;
    for (const part of parts.slice(0, -1)) at = (at[part] ??= {}) as Record<string, unknown>;
    at[parts[parts.length - 1]] = value;
    live.add(name);
  }
  return { values, live };
}
