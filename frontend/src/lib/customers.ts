import type { Role } from "./roles.js";

/** How much of a customer someone sees (backend/app/customers.py). */
export type Visibility = "full" | "metadata" | "names";

export interface Site {
  id: number;
  name: string;
  address: string;
}

export interface Contact {
  id: number;
  name: string;
  role: string;
  email: string;
  phone: string;
}

export interface Person {
  id: number;
  username: string;
  display_name: string;
  roles: Role[];
}

export interface CustomerSummary {
  id: number;
  name: string;
  visibility: Visibility;
  cvr: string | null;
  active_projects: number | null;
  archived_projects: number | null;
  logo_url: string | null;
}

export interface CustomerDetail extends CustomerSummary {
  address: string | null;
  language: "da" | "en" | null;
  retention_months: number | null;
  created_at: string | null;
  sites: Site[] | null;
  contacts: Contact[] | null;
  assigned: Person[] | null;
  may_manage: boolean;
  may_create_projects: boolean;
  assignable: Person[] | null;
}

export interface Named {
  id: number;
  name: string;
}

export interface ProjectSummary {
  id: number;
  number: string;
  name: string;
  customer: Named;
  responsible: Named | null;
  start_date: string | null;
  end_date: string | null;
  classification: Classification;
  archived_at: string | null;
}

/** Someone on a project's team: its responsible technician or someone added. */
export interface Member extends Named {
  roles: Role[];
  responsible: boolean;
}

export interface ProjectDetail extends ProjectSummary {
  contact: Named | null;
  sites: Named[];
  team: Member[];
  created_at: string;
  may_edit: boolean;
  may_reopen: boolean;
}

export const LANGUAGES = [
  { value: "da", name: "Danish" },
  { value: "en", name: "English" },
] as const;

// Traffic Light Protocol 2.0: who a report may be shared with.
export const CLASSIFICATIONS = [
  { value: "TLP:CLEAR", hint: "Anyone may see it." },
  { value: "TLP:GREEN", hint: "The customer's community, not public." },
  { value: "TLP:AMBER", hint: "The customer's organisation and those who need it to protect it." },
  { value: "TLP:AMBER+STRICT", hint: "The customer's organisation only." },
  { value: "TLP:RED", hint: "Only administrators and the project's team." },
] as const;

export type Classification = (typeof CLASSIFICATIONS)[number]["value"];

export const DEFAULT_CLASSIFICATION: Classification = "TLP:AMBER";

/** The classification whose projects only administrators and the team see. */
export const TEAM_ONLY = "TLP:RED";

/** The tone of a classification's label: red for the most restricted. */
export function classificationTone(value: string): "critical" | "warning" | "ok" | "neutral" {
  if (value === TEAM_ONLY) return "critical";
  if (value.startsWith("TLP:AMBER")) return "warning";
  if (value === "TLP:GREEN") return "ok";
  return "neutral";
}

/** "12 34 56 78": a CVR number in the groups people read it in. */
export function formatCvr(cvr: string | null): string {
  return cvr ? cvr.replace(/(\d{2})(?=\d)/g, "$1 ") : "—";
}

export function technicians(people: Person[] | null): Person[] {
  return (people ?? []).filter((p) => p.roles.includes("technician"));
}
