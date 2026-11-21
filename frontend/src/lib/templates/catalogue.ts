// The names the rule editors offer, labelled for people: each answer by its question,
// the report's context by what it is, the library by its name. Repeating groups carry
// their columns, and dropdowns their choices, so a rule can pick from them.

import { settingsOf, typeCode } from "./fields";
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
  /** For an answer, its question's field type. */
  field?: string;
  /**
   * For a name read from a list's rows (rowNames): the list, and the column read, from
   * the first row or, with every, from each row; no column for how many rows.
   */
  of?: { list: string; column: string | null; every?: boolean };
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

/** Every name, labelled and grouped: a template's answers first (none without a template). */
export function catalogue(content: TemplateContent | null, library: Record<string, string> = {}, labels: Record<string, string> = {}): NameEntry[] {
  const entries: NameEntry[] = [];
  const seen = new Set<string>();
  for (const q of content ? questionsOf(content) : []) {
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
        field: q.type,
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

const COLUMN_TYPES: Record<Shape, string> = { text: "string", number: "double", whole: "int", bool: "bool", date: "timestamp", texts: "list<string>", rows: "dyn", other: "dyn" };

/**
 * What text can print from a repeating group's or table's rows, which can't be printed
 * whole: how many rows there are, each column of the first row (answers.x[0], counting
 * from 0), and a text column from every row, joined.
 */
export function rowNames(entry: NameEntry): NameEntry[] {
  if (entry.shape !== "rows" || !entry.columns) return [];
  const base = { group: entry.group, field: entry.field };
  return [
    { ...base, name: `size(${entry.name})`, label: `${entry.label}: how many rows`, type: "int", shape: "whole", of: { list: entry.name, column: null } },
    ...entry.columns.map((c): NameEntry => ({
      ...base, name: `${entry.name}[0].${c.key}`, label: `${entry.label}: ${c.label}, first row`, type: COLUMN_TYPES[c.shape], shape: c.shape, choices: c.choices,
      of: { list: entry.name, column: c.key },
    })),
    ...entry.columns.filter((c) => c.shape === "text").map((c): NameEntry => ({
      ...base, name: `${entry.name}.map(row, row.${c.key}).join(", ")`, label: `${entry.label}: ${c.label}, every row`, type: "string", shape: "text",
      of: { list: entry.name, column: c.key, every: true },
    })),
  ];
}

/** A name as lists to choose from show it: an answer with its question's shorthand. */
export function entryChoice(entry: NameEntry): string {
  return entry.field ? `${typeCode(entry.field)} · ${entry.label}` : entry.label;
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
