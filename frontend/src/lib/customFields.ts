// Custom fields (backend/app/custom_fields.py): details the company keeps about customers
// and projects beyond the built-in ones. Templates read them as customer.custom.<key> and
// project.custom.<key>; the values are sealed with the customer's details.

import { api } from "#lib/api.js";

export type AppliesTo = "customer" | "project";
export type CustomFieldType = "text" | "long_text" | "number" | "date" | "yes_no" | "dropdown" | "email" | "phone";

export interface CustomField {
  id: number;
  applies_to: AppliesTo;
  key: string;
  label: string;
  type: CustomFieldType;
  help: string;
  options: string[];
  position: number;
  archived: boolean;
}

export const CUSTOM_TYPES: { type: CustomFieldType; label: string; cel: string; example: unknown }[] = [
  { type: "text", label: "Text", cel: "string", example: "SLA-2026-17" },
  { type: "long_text", label: "Long text", cel: "string", example: "Call the service desk before visiting." },
  { type: "number", label: "Number", cel: "double", example: 12 },
  { type: "date", label: "Date", cel: "timestamp", example: "2027-03-01" },
  { type: "yes_no", label: "Yes or no", cel: "bool", example: true },
  { type: "dropdown", label: "Dropdown", cel: "string", example: "" },
  { type: "email", label: "Email", cel: "string", example: "servicedesk@fjordvik.example" },
  { type: "phone", label: "Phone", cel: "string", example: "+45 70 20 30 40" },
];

export const customFieldsApi = {
  list: (archived = false) => api<CustomField[]>("GET", `/custom-fields${archived ? "?archived=true" : ""}`),
  create: (body: { applies_to: AppliesTo; key: string; label: string; type: CustomFieldType; help: string; options: string[] }) =>
    api<CustomField>("POST", "/custom-fields", body),
  update: (id: number, body: { label: string; help: string; options: string[]; position: number; archived: boolean }) =>
    api<CustomField>("PUT", `/custom-fields/${id}`, body),
};

function typeOf(field: CustomField) {
  return CUSTOM_TYPES.find((t) => t.type === field.type) ?? CUSTOM_TYPES[0];
}

/** The names templates read the fields in use by, with their types. */
export function customNames(fields: CustomField[]): Record<string, string> {
  return Object.fromEntries(fields.filter((f) => !f.archived).map((f) => [`${f.applies_to}.custom.${f.key}`, typeOf(f).cel]));
}

/** What each name is, for the Data tab and the rule editors. */
export function customLabels(fields: CustomField[]): Record<string, string> {
  return Object.fromEntries(fields.filter((f) => !f.archived).map((f) => [`${f.applies_to}.custom.${f.key}`, f.label]));
}

/** An example value for each field in use, by key, for previews: a dropdown's first option. */
export function sampleCustom(fields: CustomField[], appliesTo: AppliesTo): Record<string, unknown> {
  const found: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.archived || f.applies_to !== appliesTo) continue;
    found[f.key] = f.type === "dropdown" ? (f.options[0] ?? "") : typeOf(f).example;
  }
  return found;
}
