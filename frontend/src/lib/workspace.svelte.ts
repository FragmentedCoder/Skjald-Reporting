import { api, BACKGROUND } from "./api.js";
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
  // Goes up on every refresh, so open pages can check they're still allowed.
  checks: number;
  // Whether the last refresh was the timer's own, not someone's doing: what open pages
  // ask because of it is asked the same way (see BACKGROUND in api.ts).
  background: boolean;
}>({ customers: null, customerId: null, projects: null, project: null, checks: 0, background: false });

let lastRefresh = 0;

/** The customer's active projects. The open project is newer than the list: one just
 * archived goes under Archived at once, not in both places until the list is fetched
 * again. */
export function activeProjects(
  projects: ProjectSummary[] | null,
  open: ProjectSummary | null,
): ProjectSummary[] {
  return (projects ?? []).filter((project) => !(open?.archived_at && project.id === open.id));
}

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

async function loadProjects(headers: Record<string, string> = {}): Promise<void> {
  const open = openCustomer();
  workspace.projects =
    open?.visibility === "full"
      ? await api<ProjectSummary[]>("GET", `/customers/${open.id}/projects`, undefined, headers).catch(() => [])
      : null;
}

/**
 * Fetch the customers again (names, counts) and the open one's projects. In the
 * background (the timer's refresh, or coming back to the page) it doesn't count as
 * activity, so the menu keeping itself up to date never keeps a session alive.
 */
export async function refreshWorkspace(background = false): Promise<void> {
  lastRefresh = Date.now();
  const headers = background ? { ...BACKGROUND } : {};
  const found = await api<CustomerSummary[]>("GET", "/customers", undefined, headers).catch(() => null);
  // A failed request (offline, signed out) keeps what's there rather than emptying it.
  if (found === null && workspace.customers !== null) return;
  workspace.customers = found ?? [];
  if (workspace.customerId === null) workspace.customerId = remembered();
  if (workspace.customerId !== null && !openCustomer()) workspace.customerId = null;
  await loadProjects(headers);
  workspace.background = background;
  workspace.checks++;
}

/** Refresh unless that happened in the last few seconds (as on every page change). */
export function refreshSoon(background = false): void {
  if (Date.now() - lastRefresh > 15_000) void refreshWorkspace(background);
}

/**
 * Notice access that changed while the app is open (someone unassigned you, a
 * customer was deleted): refresh every minute while the page is in view, and on
 * coming back to it. Returns the function that stops watching.
 */
export function watchWorkspace(): () => void {
  const visible = () => {
    if (document.visibilityState === "visible") refreshSoon(true);
  };
  const timer = setInterval(() => {
    if (document.visibilityState === "visible") void refreshWorkspace(true);
  }, 60_000);
  document.addEventListener("visibilitychange", visible);
  window.addEventListener("focus", visible);
  return () => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", visible);
    window.removeEventListener("focus", visible);
  };
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
