// Skjald's function library in the browser: what templates may call, and the
// functions Skjald adds to cel-js. The list itself is shared/cel/functions.json, read
// here directly; the server's copy (backend/app/cel/library.py) is held to it by a test.

import { RE2JS } from "re2js";
import { celFunctions as shared } from "#lib/shared.js";
import { addDays, daysBetween, formatDate, hoursBetween, parseDate, type Locale } from "./dates";
import { characters } from "./lexer";
import { digitsOf, formatNumber } from "./numbers";

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

// Functions Skjald gives under a name of its own in the browser, because cel-js has
// one by that name that behaves differently from the server's: its upperAscii()
// changes æ, its substring() counts an emoji as two, its int("") is 0. An expression's
// int(...) is rewritten to skjald_int(...) before cel-js sees it (engine.ts), and
// back in what's said about it.
export const ALIAS = "skjald_";
export const ALIASED = new Set(["int", "double", "string", "upperAscii", "lowerAscii", "trim", "split", "substring", "indexOf"]);

/** A signature from the shared list under the name the browser registers it by. */
export const aliased = (signature: string) =>
  signature.replace(/^((?:.+\.)?)(\w+)\(/, (_all, receiver: string, name: string) => `${receiver}${ALIASED.has(name) ? ALIAS : ""}${name}(`);

/**
 * How each function is written: by name and whether it comes after a value and a dot
 * ("size:true", "size:false"), how many values go inside its brackets.
 */
export function forms(): Map<string, Set<number>> {
  const found = new Map<string, Set<number>>();
  for (const { signature } of FUNCTIONS.flatMap((f) => f.overloads)) {
    const match = /^(?:(.+)\.)?(\w+)\((.*)\):\s*.+$/.exec(signature);
    if (!match) throw new Error(`Bad signature '${signature}'.`);
    const [, receiver, name, params] = match;
    let depth = 0;
    let count = params.trim() ? 1 : 0;
    for (const c of params) {
      if (c === "<") depth += 1;
      if (c === ">") depth -= 1;
      if (c === "," && depth === 0) count += 1;
    }
    const key = `${name}:${receiver !== undefined}`;
    found.set(key, (found.get(key) ?? new Set()).add(count));
  }
  return found;
}

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
export const PATTERN = "The pattern isn't a regular expression Skjald can use (RE2 syntax).";

/** A regular expression both sides can use: RE2's syntax. */
export function regex(pattern: string): RE2JS {
  let found = patterns.get(pattern);
  if (!found) {
    try {
      found = RE2JS.compile(pattern);
    } catch {
      throw new Error(PATTERN);
    }
    if (patterns.size > 256) patterns.clear();
    patterns.set(pattern, found);
  }
  return found;
}

const isDigit = (c: string | undefined) => c !== undefined && c >= "0" && c <= "9";

/**
 * Skjald's replacement text as plain text and group numbers: $1 or ${1} is a group by
 * number, ${name} one by name, $0 the whole match and $$ a dollar sign.
 */
export function replacementParts(replacement: string, groups: number, names: Record<string, number>): (string | number)[] {
  const parts: (string | number)[] = [];
  for (let i = 0; i < replacement.length; i++) {
    const c = replacement[i];
    let written: string | null = null;
    if (c !== "$") {
      parts.push(c);
    } else if (replacement.startsWith("$$", i)) {
      parts.push("$");
      i += 1;
    } else if (replacement.startsWith("${", i) && replacement.indexOf("}", i) > 0) {
      const end = replacement.indexOf("}", i);
      written = replacement.slice(i + 2, end);
      i = end;
    } else if (isDigit(replacement[i + 1])) {
      let j = i + 1;
      while (isDigit(replacement[j])) j += 1;
      written = replacement.slice(i + 1, j);
      i = j - 1;
    } else {
      parts.push("$");
    }
    if (written !== null) {
      const numbered = /^[0-9]+$/.test(written);
      const group = numbered ? Number(written) : Object.hasOwn(names, written) ? names[written] : -1;
      if (!(group >= 0 && group <= groups)) {
        const shown = numbered && replacement[i] !== "}" ? `$${written}` : `\${${written}}`;
        throw new Error(`The replacement uses ${shown}, a group the pattern doesn't have.`);
      }
      parts.push(group);
    }
  }
  return parts;
}

function reReplace(text: string, pattern: string, replacement: string): string {
  const compiled = regex(pattern);
  const parts = replacementParts(replacement, compiled.groupCount(), compiled.namedGroups());
  return compiled
    .matcher(text)
    .replaceAll((...found: unknown[]) => parts.map((part) => (typeof part === "string" ? part : ((found[part] as string | undefined) ?? ""))).join(""));
}

const MAX_INT = 2n ** 63n - 1n;
const TOO_LARGE = "The result is too large for a whole number.";

function sum(items: unknown[]): bigint | number {
  if (items.every((x) => typeof x === "bigint")) return (items as bigint[]).reduce((a, b) => a + b, 0n);
  return items.reduce<number>((a, b) => a + Number(b), 0);
}

function intFromText(text: string): bigint {
  if (!/^[+-]?[0-9]+$/.test(text)) throw new Error(`int() can't read '${text}' as a whole number.`);
  const value = BigInt(text);
  if (value > MAX_INT || value < -MAX_INT - 1n) throw new Error(TOO_LARGE);
  return value;
}

function intFromDouble(value: number): bigint {
  if (!Number.isFinite(value) || value <= -(2 ** 63) || value >= 2 ** 63) throw new Error(TOO_LARGE);
  return BigInt(Math.trunc(value));
}

function doubleFromText(text: string): number {
  const value = /^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(text) ? Number(text) : NaN;
  if (!Number.isFinite(value)) throw new Error(`double() can't read '${text}' as a number.`);
  return value;
}

/** A decimal as it's written, never with an exponent: 1234567.5, 0.0000001. */
function textFromDouble(value: number): string {
  if (!Number.isFinite(value)) throw new Error("string() needs a finite number.");
  if (value === 0) return "0";
  const { negative, whole, fraction } = digitsOf(value);
  return `${negative ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

// What trim() takes away at either end: the characters Unicode calls white space, as
// the server's engine does (JavaScript's own trim() differs on two of them).
const WHITE = "\\t\\n\\v\\f\\r \\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const ENDS = new RegExp(`^[${WHITE}]+|[${WHITE}]+$`, "g");
const SUBSTRING = "substring() takes two positions from 0 to the length of the text, the first no larger than the second.";

function substring(text: string, start: bigint, end: bigint): string {
  const all = Array.from(text);
  if (start < 0n || end < start || end > BigInt(all.length)) throw new Error(SUBSTRING);
  return all.slice(Number(start), Number(end)).join("");
}

function indexOf(text: string, search: string): bigint {
  const at = text.indexOf(search);
  return BigInt(at < 0 ? -1 : characters(text.slice(0, at)));
}

function split(text: string, separator: string): string[] {
  if (separator !== "") return text.split(separator);
  return text === "" ? [""] : Array.from(text);
}

function replace(text: string, from: string, to: string): string {
  if (from !== "") return text.split(from).join(to);
  return to + Array.from(text).map((c) => c + to).join("");
}

/** date() of a text: a moment in the years 1 to 9999, as the server's dates are. */
export function dateFrom(text: string, zone: string): Date {
  const moment = parseDate(text, zone);
  const year = moment.getUTCFullYear();
  if (year < 1 || year > 9999) throw new Error(`'${text}' isn't a date such as 2026-10-21 or 2026-10-21T14:30.`);
  return moment;
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
    int_string: intFromText,
    int_double: intFromDouble,
    int_int: (value: bigint) => value,
    double_string: doubleFromText,
    double_int: (value: bigint) => Number(value),
    double_double: (value: number) => value,
    string_int: (value: bigint) => value.toString(),
    string_double: textFromDouble,
    string_bool: (value: boolean) => (value ? "true" : "false"),
    string_string: (value: string) => value,
    re_match_string_string: (text: string, pattern: string) => regex(pattern).matcher(text).find(),
    re_replace_string_string_string: reReplace,
    string_replace_string_string: replace,
    string_upper_ascii: (text: string) => text.replace(/[a-z]/g, (c) => c.toUpperCase()),
    string_lower_ascii: (text: string) => text.replace(/[A-Z]/g, (c) => c.toLowerCase()),
    string_trim: (text: string) => text.replace(ENDS, ""),
    string_split_string: split,
    substring_int_int: substring,
    string_index_of_string: indexOf,
    format_number_double_int: (value: number, places: bigint) =>
      formatNumber(value, Number(places), locale.decimal, locale.group),
    format_number_int_int: (value: bigint, places: bigint) =>
      formatNumber(value, Number(places), locale.decimal, locale.group),
    sum_list: sum,
    lookup_string_string: (table: string, key: string) => lookup(context, table, key),
    lookup_string_string_string: (table: string, key: string, column: string) =>
      lookup(context, table, key, column),
    date_string: (text: string) => dateFrom(text, zone),
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
