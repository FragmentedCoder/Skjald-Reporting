// The names the rule editors offer, labelled for people: each answer by its question,
// the report's context by what it is, the library by its name. Repeating groups carry
// their columns, and dropdowns their choices, so a rule can pick from them.

import { settingsOf } from "./fields";
import { CONTEXT_GROUPS, questionNames } from "./names";
import { shapeOf, type Shape } from "./rules";
import { questionsOf, type TemplateContent } from "./types";

export interface Choice {
  value: string;
  label: string;
}

export interface Column {
  key: string;
  label: string;
  shape: Shape;
  choices?: Choice[];
}

export interface NameEntry {
  name: string;
  label: string;
  group: string;
  type: string;
  shape: Shape;
  choices?: Choice[];
  columns?: Column[];
}

const PARTS: Record<string, string> = {
  ".score": "score",
  ".vector": "vector",
  ".severity": "severity",
  ".filled": "is filled in",
  ".printed": "as printed",
  ".count": "how many",
};

type RawColumn = { key: string; label: string; type: string; settings?: Record<string, unknown> };

function columnsOf(settings: Record<string, unknown>): Column[] {
  return ((settings.columns ?? []) as RawColumn[]).map((c) => ({
    key: c.key,
    label: c.label,
    shape: shapeOf(columnType(c)),
    choices: c.type === "dropdown" ? ((c.settings?.options ?? []) as Choice[]) : undefined,
  }));
}

function columnType(column: RawColumn): string {
  if (column.type === "number") return column.settings?.whole ? "int" : "double";
  if (column.type === "yes_no") return "bool";
  if (column.type === "datetime") return "timestamp";
  return "string";
}

export function catalogue(content: TemplateContent, library: Record<string, string> = {}, labels: Record<string, string> = {}): NameEntry[] {
  const entries: NameEntry[] = [];
  const seen = new Set<string>();
  for (const q of questionsOf(content)) {
    const settings = settingsOf(q.type, q.settings);
    for (const [name, type] of Object.entries(questionNames(q))) {
      if (seen.has(name)) continue;
      seen.add(name);
      const suffix = name.slice(`answers.${q.key}`.length);
      entries.push({
        name,
        label: suffix ? `${q.label}: ${PARTS[suffix] ?? suffix.slice(1)}` : q.label,
        group: "Answers",
        type,
        shape: shapeOf(type),
        choices: q.type === "dropdown" || q.type === "multi_select" ? (settings.options as Choice[]) : undefined,
        columns: q.type === "repeating" || q.type === "table" ? columnsOf(settings) : undefined,
      });
    }
  }
  for (const group of CONTEXT_GROUPS) {
    for (const n of group.names) {
      entries.push({ name: n.name, label: n.description.replace(/\.$/, ""), group: group.label, type: n.type, shape: shapeOf(n.type) });
    }
  }
  for (const [name, type] of Object.entries(library)) {
    const group = name.startsWith("customer.custom.") ? "Customer: custom fields" : name.startsWith("project.custom.") ? "Project: custom fields" : "Library";
    entries.push({ name, label: labels[name] || name, group, type, shape: shapeOf(type) });
  }
  return entries;
}

/** The shapes of every name, row columns included (as row.<key>), for rules.ts. */
export function shapes(entries: NameEntry[]): Record<string, Shape> {
  const found: Record<string, Shape> = {};
  for (const entry of entries) {
    found[entry.name] = entry.shape;
    for (const column of entry.columns ?? []) found[`row.${column.key}`] ??= column.shape;
  }
  return found;
}
