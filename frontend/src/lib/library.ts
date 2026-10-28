// The shared library (backend/app/library): what the API sends and takes, and what
// templates read from it: vars.<key>, text.<key> with its variables filled in, and
// the data tables for lookup().

import { api } from "#lib/api.js";
import type { Table } from "#lib/cel/library.js";
import { interpolations } from "#lib/templates/text.js";

export type LibraryKind = "variable" | "snippet" | "table";

export interface TableValue {
  key_label: string;
  columns: string[];
  rows: Record<string, string[]>;
}

export type LibraryValue = { value: string } | { text: string } | TableValue;

export interface LibraryEntry {
  id: number;
  kind: LibraryKind;
  key: string;
  description: string;
  value: LibraryValue;
  version: number;
  updated_at: string;
  updated_by: string | null;
  locked: boolean;
  locked_by: string | null;
}

export interface LibraryVersion {
  number: number;
  value: LibraryValue;
  saved_at: string;
  saved_by: string | null;
}

export const libraryApi = {
  list: () => api<LibraryEntry[]>("GET", "/library"),
  create: (kind: LibraryKind, key: string, description: string, value: LibraryValue) =>
    api<LibraryEntry>("POST", "/library", { kind, key, description, value }),
  update: (id: number, version: number, description: string, value: LibraryValue) =>
    api<LibraryEntry>("PUT", `/library/${id}`, { version, description, value }),
  remove: (id: number) => api<void>("DELETE", `/library/${id}`),
  versions: (id: number) => api<LibraryVersion[]>("GET", `/library/${id}/versions`),
  lock: (id: number) => api<LibraryEntry>("POST", `/library/${id}/lock`),
  unlock: (id: number) => api<LibraryEntry>("POST", `/library/${id}/unlock`),
  importTable: (id: number, file: File) =>
    api<LibraryEntry>("POST", `/library/${id}/import?format=${file.name.toLowerCase().endsWith(".json") ? "json" : "csv"}`, file),
};

/** The names templates read from the library, and their types. */
export function libraryNames(entries: LibraryEntry[]): Record<string, string> {
  const names: Record<string, string> = {};
  for (const e of entries) {
    if (e.kind === "variable") names[`vars.${e.key}`] = "string";
    if (e.kind === "snippet") names[`text.${e.key}`] = "string";
  }
  return names;
}

/** What templates read: variables, snippets with their variables filled in, and tables. */
export function libraryValues(entries: LibraryEntry[]): { values: Record<string, Record<string, string>>; tables: Record<string, Table> } {
  const vars: Record<string, string> = {};
  const text: Record<string, string> = {};
  const tables: Record<string, Table> = {};
  for (const e of entries) {
    if (e.kind === "variable") vars[e.key] = (e.value as { value: string }).value;
    if (e.kind === "table") tables[e.key] = { columns: (e.value as TableValue).columns, rows: (e.value as TableValue).rows };
  }
  for (const e of entries) {
    if (e.kind !== "snippet") continue;
    const source = (e.value as { text: string }).text;
    let out = "";
    let last = 0;
    for (const found of interpolations(source)) {
      out += source.slice(last, found.start) + (vars[found.expr.split(".")[1]] ?? "");
      last = found.end;
    }
    text[e.key] = out + source.slice(last);
  }
  return { values: { vars, text }, tables };
}

/** How templates name an entry: vars.x, text.x or lookup("x", …). */
export function entryName(entry: { kind: LibraryKind; key: string }): string {
  return entry.kind === "variable" ? `vars.${entry.key}` : entry.kind === "snippet" ? `text.${entry.key}` : `lookup("${entry.key}", key)`;
}
