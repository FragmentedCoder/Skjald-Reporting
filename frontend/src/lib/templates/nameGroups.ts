// The names a template can read, grouped and described for people to look up: what
// each one is, its kind, and an example: from the sample data, or on the Database
// page what's there now (current.ts). The Database page, a template's Data tab and
// the editor's Names drawer show the same lists.

import { human, plain } from "#lib/cel/engine.js";
import { entryName, type LibraryEntry, type TableValue } from "#lib/library.js";
import { rowNames, type NameEntry } from "./catalogue";
import { CONTEXT_GROUPS } from "./names";

export interface NameRow {
  /** The name, or for a data table the lookup that reads it. */
  name: string;
  what: string;
  kind: string;
  example: string;
  /** Given current values: whether the example is one (true) or made up (false). */
  live?: boolean;
  /** For an answer, its question's field type. */
  field?: string;
}

export interface NameGroup {
  title: string;
  about: string;
  rows: NameRow[];
}

const ABOUT: Record<string, string> = {
  Answers: "What the technician fills in, by each question's variable name. Calculated values are worked out from the others. "
    + "A repeating group or table is a list of rows: size(answers.x) is how many, answers.x[0] the first row and answers.x[1] the second "
    + "(counting from 0), answers.x[0].column one of its columns, and a section can be repeated for each row.",
  "Customer: custom fields": "The company's own details about customers, filled in on the customer's settings. The examples are made up.",
  "Project: custom fields": "The company's own details about projects, filled in with the project's details. The examples are made up.",
  Library: "Shared by every template and report. A report uses the current values until it's signed, then keeps those.",
};

/** A value as the lists show it: text in quotes, nothing as a dash. */
export function shown(value: unknown): string {
  const v = plain(value);
  if (v === null || v === undefined || v === "") return "—";
  if (v instanceof Date) return v.toISOString().replace(".000Z", "Z");
  return typeof v === "string" ? `"${v}"` : JSON.stringify(v);
}

/** A name's value in the sample data, such as values.customer.name. */
export function valueOf(values: Record<string, unknown>, name: string): unknown {
  let current: unknown = values;
  for (const part of name.split(".")) current = current && typeof current === "object" ? (current as Record<string, unknown>)[part] : undefined;
  return current;
}

/** An example for a name read from a list's rows, from the list's own example. */
function rowExample(values: Record<string, unknown>, of: NonNullable<NameEntry["of"]>): unknown {
  const rows = valueOf(values, of.list);
  if (!Array.isArray(rows)) return undefined;
  if (of.column === null) return rows.length;
  const column = of.column;
  const cell = (row: unknown) => (row && typeof row === "object" ? (row as Record<string, unknown>)[column] : undefined);
  return of.every ? rows.map(cell).filter((v) => v !== null && v !== undefined && v !== "").join(", ") : cell(rows[0]);
}

/**
 * The names in their groups, in order: answers, the report's context, custom fields,
 * the library, data tables. With `live`, the names whose example is a current value;
 * the library's are always current.
 */
export function nameGroups(entries: NameEntry[], values: Record<string, unknown>, library: LibraryEntry[] = [], live?: Set<string>): NameGroup[] {
  const sources = Object.fromEntries(CONTEXT_GROUPS.map((g) => [g.label, `${g.source}.`]));
  const groups: NameGroup[] = [];
  for (const entry of entries.flatMap((e) => [e, ...rowNames(e)])) {
    let group = groups.find((g) => g.title === entry.group);
    if (!group) groups.push((group = { title: entry.group, about: ABOUT[entry.group] ?? sources[entry.group] ?? "", rows: [] }));
    const current = live && (live.has(entry.name) || /^(vars|text)\./.test(entry.name));
    group.rows.push({
      name: entry.name, what: entry.label, kind: human(entry.type), example: shown(entry.of ? rowExample(values, entry.of) : valueOf(values, entry.name)),
      ...(entry.field ? { field: entry.field } : {}), ...(live ? { live: current } : {}),
    });
  }
  const tables = library.filter((e) => e.kind === "table");
  if (tables.length) {
    groups.push({
      title: "Data tables",
      about: "Values by key, from the library: read one with lookup(\"table\", key), or a column with lookup(\"table\", key, \"column\").",
      rows: tables.map((e) => {
        const t = e.value as TableValue;
        const n = Object.keys(t.rows).length;
        return { name: entryName(e), what: e.description || e.key, kind: "data table", example: `${n} row${n === 1 ? "" : "s"}: ${t.key_label} → ${t.columns.join(", ")}`, ...(live ? { live: true } : {}) };
      }),
    });
  }
  return groups;
}

/** The groups with only the names matching every word searched for, in their name, what they are or their group. */
export function searchNames(groups: NameGroup[], query: string): NameGroup[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return groups;
  return groups
    .map((g) => ({ ...g, rows: g.rows.filter((r) => words.every((w) => `${r.name} ${r.what} ${g.title}`.toLowerCase().includes(w))) }))
    .filter((g) => g.rows.length);
}
