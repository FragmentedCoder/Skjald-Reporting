import { api } from "./api.js";
import type { CustomerSummary, ProjectSummary } from "./customers.js";

// What the side menu works from: the customers someone can pick, the one that's
// open, its active projects (listed under it), and the open project (which may be
// archived). Only the chosen customer's ID is remembered on this device, never
// its name.

const REMEMBERED = "skjald.customer";

export const workspace = $state<{
  customers: CustomerSummary[] | null;
  customerId: number | null;
  projects: ProjectSummary[] | null;
  project: ProjectSummary | null;
}>({ customers: null, customerId: null, projects: null, project: null });

export function openCustomer(): CustomerSummary | null {
  return workspace.customers?.find((c) => c.id === workspace.customerId) ?? null;
}

function remember(id: number | null): void {
  try {
    if (id === null) localStorage.removeItem(REMEMBERED);
    else localStorage.setItem(REMEMBERED, String(id));
  } catch {
    // Private windows and blocked storage: the menu just starts without a customer.
  }
}

function remembered(): number | null {
  try {
    const id = Number(localStorage.getItem(REMEMBERED));
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

async function loadProjects(): Promise<void> {
  const open = openCustomer();
  workspace.projects =
    open?.visibility === "full"
      ? await api<ProjectSummary[]>("GET", `/customers/${open.id}/projects`).catch(() => [])
      : null;
}

/** Fetch the customers again (names, counts) and the open one's projects. */
export async function refreshWorkspace(): Promise<void> {
  workspace.customers = await api<CustomerSummary[]>("GET", "/customers").catch(() => []);
  if (workspace.customerId === null) workspace.customerId = remembered();
  if (workspace.customerId !== null && !openCustomer()) workspace.customerId = null;
  await loadProjects();
}

/** Open a customer in the menu, and one of its projects (and remember the customer). */
export async function chooseCustomer(id: number | null, project: ProjectSummary | null = null) {
  const changed = workspace.customerId !== id;
  workspace.customerId = id;
  workspace.project = project;
  remember(id);
  // A customer the list doesn't know yet (just added, or newly assigned) fetches it again.
  if (workspace.customers === null || (id !== null && !openCustomer())) await refreshWorkspace();
  else if (changed) await loadProjects();
}

/** Forget everything about the workspace, as on signing out. */
export function clearWorkspace(): void {
  workspace.customers = null;
  workspace.customerId = null;
  workspace.projects = null;
  workspace.project = null;
}
