// Skjald's function library in the browser: what templates may call, and the
// functions Skjald adds to cel-js. The list itself is shared/cel/functions.json, read
// here directly; the server's copy (backend/app/cel/library.py) is held to it by a test.

import { RE2JS } from "re2js";
import { celFunctions as shared } from "#lib/shared.js";
import { addDays, daysBetween, formatDate, hoursBetween, parseDate, type Locale } from "./dates";
import { formatNumber } from "./numbers";

export type Where = "skjald" | "engine" | "browser";

export interface Overload {
  id: string;
  signature: string;
  where: Where;
}

export interface FunctionInfo {
  name: string;
  group: string;
  summary: string;
  overloads: Overload[];
  examples: { expr: string; result: unknown }[];
}

export const FUNCTIONS = shared.functions as FunctionInfo[];
export const BANNED: Record<string, string> = shared.banned;
export const ALLOWED = new Set(FUNCTIONS.map((f) => f.name));
export const LOCALES = shared.locales as Record<string, Locale>;

/** A shared library data table: rows of values by key, one per column. */
export interface Table {
  columns: string[];
  rows: Record<string, string[]>;
}

export interface Context {
  zone: string;
  locale: Locale;
  tables: Record<string, Table>;
}

type CelMap = Map<unknown, unknown> | Record<string, unknown>;

const get = (map: CelMap, key: unknown, fallback: unknown) => {
  if (map instanceof Map) return map.has(key) ? map.get(key) : fallback;
  return Object.hasOwn(map, String(key)) ? map[String(key)] : fallback;
};

const patterns = new Map<string, RE2JS>();

function regex(pattern: string): RE2JS {
  let found = patterns.get(pattern);
  if (!found) {
    found = RE2JS.compile(pattern);
    if (patterns.size > 256) patterns.clear();
    patterns.set(pattern, found);
  }
  return found;
}

/**
 * Skjald's replacement text ($1, ${name}, $$; a backslash is just a backslash) as
 * re2js's JavaScript-style text ($1, $<name>, $& for the whole match, $$).
 */
export function replacementTemplate(replacement: string): string {
  let out = "";
  for (let i = 0; i < replacement.length; i++) {
    const c = replacement[i];
    if (c !== "$") {
      out += c;
    } else if (replacement.startsWith("$$", i)) {
      out += "$$";
      i += 1;
    } else if (replacement.startsWith("${", i) && replacement.indexOf("}", i) > 0) {
      const end = replacement.indexOf("}", i);
      out += `$<${replacement.slice(i + 2, end)}>`;
      i = end;
    } else if (/\d/.test(replacement[i + 1] ?? "")) {
      let j = i + 1;
      while (j < replacement.length && /\d/.test(replacement[j])) j += 1;
      const group = replacement.slice(i + 1, j);
      out += Number(group) === 0 ? "$&" : `$${group}`;
      i = j - 1;
    } else {
      out += "$$";
    }
  }
  return out;
}

function sum(items: unknown[]): bigint | number {
  if (items.every((x) => typeof x === "bigint")) return (items as bigint[]).reduce((a, b) => a + b, 0n);
  return items.reduce<number>((a, b) => a + Number(b), 0);
}

function lookup(context: Context, table: string, key: string, column?: string): string {
  const found = context.tables[table];
  if (!found || !Object.hasOwn(found.rows, key)) return "";
  const index = column === undefined ? 0 : found.columns.indexOf(column);
  return index >= 0 ? (found.rows[key][index] ?? "") : "";
}

/** The implementations of every overload Skjald adds in the browser, by ID. */
export function implementations(context: Context): Record<string, (...args: never[]) => unknown> {
  const { zone, locale } = context;
  const pick = (value: unknown, cases: CelMap, fallback: unknown) => get(cases, value, fallback);
  return {
    xor_bool_bool: (a: boolean, b: boolean) => a !== b,
    switch_string_string: pick,
    switch_int_string: pick,
    switch_string_double: pick,
    switch_string_int: pick,
    re_match_string_string: (text: string, pattern: string) => regex(pattern).matcher(text).find(),
    re_replace_string_string_string: (text: string, pattern: string, replacement: string) =>
      regex(pattern).matcher(text).replaceAll(replacementTemplate(replacement)),
    string_replace_string_string: (text: string, from: string, to: string) => text.split(from).join(to),
    format_number_double_int: (value: number, places: bigint) =>
      formatNumber(value, Number(places), locale.decimal, locale.group),
    format_number_int_int: (value: bigint, places: bigint) =>
      formatNumber(value, Number(places), locale.decimal, locale.group),
    sum_list: sum,
    lookup_string_string: (table: string, key: string) => lookup(context, table, key),
    lookup_string_string_string: (table: string, key: string, column: string) =>
      lookup(context, table, key, column),
    date_string: (text: string) => parseDate(text, zone),
    add_hours_timestamp_int: (moment: Date, hours: bigint) => new Date(moment.getTime() + Number(hours) * 3_600_000),
    add_days_timestamp_int: (moment: Date, days: bigint) => addDays(moment, Number(days), zone),
    hours_between_timestamp_timestamp: hoursBetween,
    days_between_timestamp_timestamp: (start: Date, end: Date) => BigInt(daysBetween(start, end, zone)),
    format_date_timestamp_string: (moment: Date, pattern: string) => formatDate(moment, pattern, zone, locale),
  };
}

/** Types written as in the shared list (timestamp) the way cel-js names them. */
export function celJsType(type: string): string {
  return type
    .replace(/\btimestamp\b/g, "google.protobuf.Timestamp")
    .replace(/\bduration\b/g, "google.protobuf.Duration");
}

/** The overloads the browser must add to cel-js, from the shared list. */
export function browserOverloads(): Overload[] {
  return FUNCTIONS.flatMap((f) => f.overloads).filter((o) => o.where !== "engine");
}
