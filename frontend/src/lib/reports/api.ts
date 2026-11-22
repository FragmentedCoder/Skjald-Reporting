// The reports API (backend/app/reports/routes.py): what it sends and takes.

import { api, BACKGROUND } from "#lib/api.js";
import type { Table } from "#lib/cel/library.js";
import type { Named } from "#lib/customers.js";
import type { Person } from "#lib/templates/preview.js";
import type { Id, TemplateContent } from "#lib/templates/types.js";

/** One checkout: a step of the form, or (no step) the whole report, held by one person. */
export interface Checkout {
  id: number;
  step: Id | null;
  holder: Named;
  taken_at: string;
  /** When its holder last saved under it. */
  active_at: string;
  /** Nobody saved under it for longer than the Administrators' setting. */
  stale: boolean;
  /** Held by whoever asked. */
  mine: boolean;
}

export interface TemplateRef {
  id: number;
  name: string;
  version: number;
}

export interface ReportSummary {
  id: number;
  number: string;
  title: string;
  status: string;
  revision: number;
  template: TemplateRef;
  author: Named | null;
  created_at: string;
  updated_at: string;
  checkouts: Checkout[];
}

export interface ReportList {
  reports: ReportSummary[];
  may_create: boolean;
}

/** A template a report can be written with, at its newest published version. */
export interface TemplateChoice {
  id: number;
  name: string;
  description: string;
  version: number;
  /** What its reports' numbers start with. */
  prefix: string;
}

/** Something that keeps a report from going for review. */
export interface Missing {
  step: Id;
  question: Id;
  message: string;
}

/** The server's verdict on the form, with the answers as it keeps them. */
export interface FormState {
  hidden: Id[];
  required: Id[];
  invalid: Record<Id, string>;
  missing: Missing[];
  errors: { element: Id; message: string }[];
}

/** What changes while a report is open: who holds what, and how often it was saved. */
export interface Activity {
  status: string;
  saves: number;
  updated_at: string;
  checkouts: Checkout[];
}

/** Someone a person question can pick, with the details reports print. */
export type ReportPerson = Person & { technician: boolean; reviewer: boolean; on_team: boolean };

export interface ReportDetail {
  id: number;
  number: string;
  title: string;
  status: string;
  revision: number;
  project: { id: number; number: string; name: string; classification: string; archived: boolean };
  customer: Named;
  /** The template version the report is pinned to, without its sample answers. */
  template: TemplateRef & { content: Omit<TemplateContent, "sample"> };
  /** The site chosen for the report; the project's sites to choose among. */
  site: Named | null;
  sites: Named[];
  author: Named | null;
  created_at: string;
  updated_at: string;
  /** By question ID. A kept secret comes masked (templates/secrets.ts). */
  answers: Record<Id, unknown>;
  /** How many times its answers were saved, by anyone. */
  saves: number;
  /** What the template's expressions read besides the answers. */
  context: Record<string, Record<string, unknown>>;
  library: { names: Record<string, string>; values: Record<string, unknown>; tables: Record<string, Table> };
  people: ReportPerson[];
  /** The template's images, by SHA-256. */
  assets: Record<string, { url: string; width: number; height: number }>;
  time_zone: string;
  checkouts: Checkout[];
  may_edit: boolean;
  may_reveal: boolean;
  may_break: boolean;
  may_discard: boolean;
  state: FormState;
}

/** What a save kept: the answers that changed, as the server keeps them, and the ones no longer answered. */
export interface Saved {
  saves: number;
  updated_at: string;
  answers: Record<Id, unknown>;
  forgotten: Id[];
}

/** A secret answer, shown for a number of seconds. */
export interface Revealed {
  value: string;
  seconds: number;
}

export interface ReportSettings {
  checkout_stale_hours: number;
}

/** The limits of backend/app/reports/models.py STALE_HOURS_LIMITS; the server checks them too. */
export const STALE_HOURS = { min: 1, max: 720 };

const base = (id: number) => `/reports/${id}`;

export const reportsApi = {
  list: (projectId: number) => api<ReportList>("GET", `/projects/${projectId}/reports`),
  /** For those who may start a report; refused for everyone else. */
  templates: (projectId: number) => api<TemplateChoice[]>("GET", `/projects/${projectId}/report-templates`),
  create: (projectId: number, body: { template_id: number; title?: string; site_id?: number | null }) =>
    api<ReportDetail>("POST", `/projects/${projectId}/reports`, body),
  // In the background: fetched again because someone else saved, not because the reader did anything.
  get: (id: number, background = false) => api<ReportDetail>("GET", base(id), undefined, background ? { ...BACKGROUND } : {}),
  /** The title or the site: for someone holding a checkout. */
  update: (id: number, change: { title?: string; site_id?: number | null }) => api<ReportDetail>("PATCH", base(id), change),
  /** Only the answers that changed; an empty one as null. */
  save: (id: number, answers: Record<Id, unknown>) => api<Saved>("PATCH", `${base(id)}/answers`, { answers }),
  // Asked on a timer, so it never counts as the reader's activity.
  activity: (id: number) => api<Activity>("GET", `${base(id)}/activity`, undefined, { ...BACKGROUND }),
  check: (id: number) => api<FormState>("POST", `${base(id)}/check`),
  /** One step, or (null) the whole report. */
  checkOut: (id: number, step: Id | null) => api<Activity>("POST", `${base(id)}/checkouts`, { step }),
  release: (id: number, checkout: number) => api<Activity>("DELETE", `${base(id)}/checkouts/${checkout}`),
  /** Ends someone else's checkout: for Administrators. */
  endCheckout: (id: number, checkout: number) => api<Activity>("POST", `${base(id)}/checkouts/${checkout}/break`),
  /** Asks for a fresh confirmation first (stepUp.svelte.ts). */
  reveal: (id: number, question: Id) => api<Revealed>("POST", `${base(id)}/answers/${encodeURIComponent(question)}/reveal`),
  discard: (id: number, confirmNumber: string) => api<void>("DELETE", base(id), { confirm_number: confirmNumber }),
  settings: () => api<ReportSettings>("GET", "/admin/report-settings"),
  saveSettings: (settings: ReportSettings) => api<ReportSettings>("PUT", "/admin/report-settings", settings),
};

export type ReportsApi = typeof reportsApi;

const STATUSES: Record<string, { label: string; tone: "ok" | "warning" | "info" | "neutral" }> = {
  draft: { label: "Draft", tone: "info" },
  in_review: { label: "In review", tone: "warning" },
  signing: { label: "Signing", tone: "warning" },
  signed: { label: "Signed", tone: "ok" },
  delivered: { label: "Delivered", tone: "ok" },
  archived: { label: "Archived", tone: "neutral" },
};

/** A report's state as a pill shows it. Only drafts exist so far; the others come with review and signing. */
export function statusOf(status: string): { label: string; tone: "ok" | "warning" | "info" | "neutral" } {
  const words = status.replaceAll("_", " ");
  return STATUSES[status] ?? { label: words.charAt(0).toUpperCase() + words.slice(1), tone: "neutral" };
}

/** What a checkout holds, in words: "the whole report", or its step by title. */
export function heldPart(checkout: Pick<Checkout, "step">, steps: { id: Id; title: string }[]): string {
  if (checkout.step === null) return "the whole report";
  const title = steps.find((s) => s.id === checkout.step)?.title;
  return title ? `the step “${title}”` : "a step";
}

/** Whether this person holds the step: it, or the whole report. */
export function holds(checkouts: Checkout[], step: Id): boolean {
  return checkouts.some((c) => c.mine && (c.step === null || c.step === step));
}

/** Whoever else holds the step (it, or the whole report), or null. */
export function heldByOther(checkouts: Checkout[], step: Id): Checkout | null {
  return checkouts.find((c) => !c.mine && (c.step === null || c.step === step)) ?? null;
}
