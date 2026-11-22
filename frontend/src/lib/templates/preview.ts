// What a template prints for a set of answers: every block worked out (rules, text
// with {{ }} expressions, repeated sections, tables, numbers), ready to be split into
// pages (pages.ts) and drawn. The builder's Layout tab and "Try it" use it with sample
// answers; it runs in the expression worker, which stops it if it takes too long.
// Phase 3's renderer does the same work on the server for the real PDF.

import { CelValue, Engine, ExpressionError, human, isSpan, plain, toCel, type EngineOptions } from "#lib/cel/engine.js";
import { formatDate, formatDuration, isMidnight, startOfDay } from "#lib/cel/dates.js";
import { LOCALES, type Table as LookupTable } from "#lib/cel/library.js";
import { formatNumber } from "#lib/cel/numbers.js";
import { fieldType, PERSON_PARTS, settingsOf } from "./fields";
import { repeatedColumns, shownAs, type LabelColumn, type LabelContext } from "./labels";
import { CONTEXT_GROUPS, declarations, ITEM } from "./names";
import { printed } from "./secrets";
import { signed } from "./signature";
import { docText, interpolations } from "./text";
import { questionsOf, type Block, type Id, type Question, type RichNode, type RichText, type Signer, type TemplateContent, type Tone } from "./types";

export interface PreviewInput {
  content: TemplateContent;
  /** Answers by question ID, as the form keeps them. */
  answers: Record<Id, unknown>;
  /** The report's context: company, customer, project and so on. */
  context: Record<string, unknown>;
  library?: { names: Record<string, string>; values: Record<string, unknown>; tables: Record<string, LookupTable> };
  /** Template images by SHA-256: where to load them from. */
  assets: Record<string, { url: string; width: number; height: number }>;
  timezone?: string;
  /** The style's text elements, by key: their words, to fill in like the template's. */
  pageTexts?: Record<string, string>;
}

export type Shown =
  | { kind: "cover"; id: Id; title: string; subtitle: string; facts: { label: string; value: string }[]; showLogo: boolean }
  | { kind: "toc"; id: Id; title: string; depth: 1 | 2 }
  | { kind: "section"; id: Id; title: string; intro: RichText | null; newPage: boolean; numbered: boolean; landscape: boolean; blocks: Shown[] }
  | { kind: "heading"; id: Id; text: string }
  | { kind: "text"; id: Id; content: RichText }
  | { kind: "answer"; id: Id; label: string | null; text: string | null; rich: RichText | null; rows: Grid | null; signature?: PrintedSignature }
  | { kind: "table"; id: Id; caption: string; grid: Grid; emptyText: string }
  | { kind: "image"; id: Id; url: string | null; caption: string; width: string; ratio: number }
  | { kind: "gallery"; id: Id; urls: string[]; caption: string; perRow: number }
  | { kind: "callout"; id: Id; tone: Tone; colour: string | null; title: string; content: RichText }
  | { kind: "severity_summary"; id: Id; caption: string; counts: { level: string; count: number }[] }
  | { kind: "sources"; id: Id; intro: string; items: { title: string; link: string }[] }
  | { kind: "signatures"; id: Id; signers: ShownSigner[]; layout: "row" | "stack"; showDate: boolean }
  | { kind: "columns"; id: Id; columns: Shown[][] }
  | { kind: "page_break"; id: Id };

export interface Grid {
  headers: string[];
  rows: string[][];
}

/** A signature question's answer as it prints: the name confirmed, and when, in the report's language. */
export interface PrintedSignature {
  name: string;
  time: string;
}

/** A signer as it's shown. One signed in the form (role "pad") has what its signature question prints, or null while it isn't signed. */
export type ShownSigner = Signer & { signed?: PrintedSignature | null };

export interface PreviewModel {
  blocks: Shown[];
  /** Blocks left out, and why, for the builder to say. */
  hidden: { id: Id; reason: string }[];
  /** Expressions that failed, by element. */
  errors: { element: Id; message: string }[];
  /** The values expressions read: answers by variable name, calculated ones included. */
  values: Record<string, unknown>;
  /** What questions not answered yet start as ("Starts as"), by question ID, as answers are kept. */
  defaults: Record<Id, unknown>;
  /** Questions and steps the form hides, and those it requires, for "Try it". */
  formHidden: Id[];
  formRequired: Id[];
  /** Answers that fail their own check: question ID and message. */
  invalid: { id: Id; message: string }[];
  /** The style's text elements, filled in. */
  pageTexts: Record<string, string>;
}

/** The sample context every preview starts from: the examples in shared/templates/names.json,
 * and custom fields' examples (customFields.ts sampleCustom) as customer.custom and project.custom. */
export function sampleContext(custom: { customer?: Record<string, unknown>; project?: Record<string, unknown> } = {}): Record<string, Record<string, unknown>> {
  const context: Record<string, Record<string, unknown>> = {};
  for (const group of CONTEXT_GROUPS) {
    for (const n of group.names) {
      const [root, part] = n.name.split(".");
      (context[root] ??= {})[part] = n.example;
    }
  }
  context.customer.custom = custom.customer ?? {};
  context.project.custom = custom.project ?? {};
  return context;
}

/** Someone a person question can pick: their business details, as author and reviewer have them. */
export type Person = { id: string; role: "technician" | "reviewer" } & Record<(typeof PERSON_PARTS)[number], string>;

/**
 * The people a person question offers in the builder: the sample report's author (a
 * technician) and reviewer. In a report they're the company's own people.
 */
export function samplePeople(context: Record<string, Record<string, unknown>>): Person[] {
  const one = (id: string, role: Person["role"], from: Record<string, unknown> = {}) =>
    ({ id, role, ...Object.fromEntries(PERSON_PARTS.map((part) => [part, String(from[part] ?? "")])) }) as Person;
  return [one("sample-author", "technician", context.author), one("sample-reviewer", "reviewer", context.reviewer)].filter((p) => p.display_name);
}

/** The people a person question lets the technician pick among. */
export function peopleFor(question: Question, people: Person[]): Person[] {
  const who = settingsOf(question.type, question.settings).who;
  return people.filter((p) => (who === "technicians" ? p.role === "technician" : who === "reviewers" ? p.role === "reviewer" : true));
}

// Answers as expressions read them

/**
 * One answer as expressions see it: a secret only as it prints, a photo only whether
 * there is one, a signature by who confirmed it and when.
 */
export function answerValue(question: Question, raw: unknown): unknown {
  const settings = settingsOf(question.type, question.settings);
  switch (question.type) {
    case "rich_text":
      return raw && typeof raw === "object" ? docText(raw as RichText) : typeof raw === "string" ? raw : "";
    case "secret": {
      const secret = typeof raw === "string" ? raw : "";
      return { filled: secret !== "", printed: printed(secret, settings.pdf as "partial" | "omit") };
    }
    case "photo":
    case "file": {
      const count = Array.isArray(raw) ? raw.length : raw ? 1 : 0;
      return { filled: count > 0, count };
    }
    case "signature": {
      // Not signed, the name is empty and the time is no date, as a date not filled in is (see noDate).
      const signature = signed(raw);
      return { filled: signature !== null, name: signature?.name ?? "", time: signature?.at ?? null };
    }
    case "person": {
      // The person as they were when picked: their details, each text.
      const picked = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
      const parts = Object.fromEntries(PERSON_PARTS.map((part) => [part, typeof picked[part] === "string" ? picked[part] : ""]));
      return { filled: parts.display_name !== "", ...parts };
    }
    case "cvss": {
      const value = (raw ?? {}) as { vector?: string; score?: number; severity?: string };
      return { vector: value.vector ?? "", score: Number(value.score ?? 0), severity: value.severity ?? "" };
    }
    case "number":
      if (typeof raw !== "number") return null;
      return settings.whole ? Math.trunc(raw) : raw;
    case "repeating":
    case "table": {
      // Each cell as its column's kind of value, so rules over the rows work whatever
      // was typed: 3 in a decimal column multiplies with 1.5, a date compares with a
      // date, and a cell left blank is the empty value of its kind.
      const columns = (settings.columns ?? []) as RowColumn[];
      const rows = Array.isArray(raw) ? (raw as (Record<string, unknown> | null)[]) : [];
      return new CelValue(rows.map((row) => Object.fromEntries(columns.map((c) => [c.key, cellValue(c, row?.[c.key])]))));
    }
    default:
      return raw ?? null;
  }
}

type RowColumn = { key: string; type: string; settings?: Record<string, unknown> };

/** One cell of a row as expressions read it, by its column's type; an empty one as that type's empty value. */
function cellValue(column: RowColumn, raw: unknown): unknown {
  switch (column.type) {
    case "number":
      if (column.settings?.whole) return typeof raw === "number" && Number.isFinite(raw) ? BigInt(Math.trunc(raw)) : 0n;
      return typeof raw === "number" && Number.isFinite(raw) ? raw : 0;
    case "yes_no":
      return raw === true;
    case "datetime": {
      const moment = typeof raw === "string" && raw ? new Date(raw) : NO_DATE;
      return Number.isNaN(moment.getTime()) ? NO_DATE : moment;
    }
    default:
      return raw === null || raw === undefined ? "" : String(raw);
  }
}

/** The date a date not filled in reaches expressions as (see noDate). */
const NO_DATE = new Date(0);

/**
 * What a question starts as, from what its rule gives, kept as its answers are: a date
 * question takes the day (midnight where the report is written), a date and time
 * question the minute. Nothing (null) when the rule gives nothing the question holds.
 */
export function startValue(question: Question, value: unknown, zone: string): unknown {
  const settings = settingsOf(question.type, question.settings);
  if (value === null || value === undefined || value === "") return null;
  if (question.type === "datetime") {
    if (!(value instanceof Date) || noDate(value)) return null;
    const moment = settings.mode === "date" ? startOfDay(value, zone) : new Date(Math.floor(value.getTime() / 60_000) * 60_000);
    return moment.toISOString();
  }
  // A number that isn't one a form holds (a rule that divides by nothing gives infinity) starts nothing.
  if (question.type === "number") return typeof value === "number" && Number.isFinite(value) ? (settings.whole ? Math.trunc(value) : value) : null;
  if (question.type === "yes_no") return typeof value === "boolean" ? value : null;
  return typeof value === "string" ? value : null;
}

/** The order calculated values are worked out in: each after the ones it reads. */
function calculationOrder(questions: Question[], engine: Engine): Question[] {
  const calculated = questions.filter((q) => q.type === "calculated" && q.key && (q.value ?? "").trim());
  const byKey = new Map(calculated.map((q) => [q.key as string, q]));
  const ordered: Question[] = [];
  const state = new Map<string, "visiting" | "done">();
  const visit = (q: Question) => {
    const key = q.key as string;
    if (state.get(key)) return;
    state.set(key, "visiting");
    let read: string[] = [];
    try {
      read = engine.references(q.value ?? "");
    } catch {
      read = [];
    }
    for (const name of read) {
      const other = byKey.get(name.split(".")[1]);
      if (name.startsWith("answers.") && other && !state.get(other.key as string)) visit(other);
    }
    state.set(key, "done");
    ordered.push(q);
  };
  calculated.forEach(visit);
  return ordered;
}

// Printing

/**
 * Whether a date is no date: one that can't be (out of range), or the one a date
 * question not answered yet reaches expressions as (the first moment of 1970, since an
 * expression's date can't be empty). Neither is printed or taken as a start value.
 */
export function noDate(value: Date): boolean {
  return Number.isNaN(value.getTime()) || value.getTime() === 0;
}

/** A value as text in {{ }} prints it, in the report's language. */
export function printValue(value: unknown, language: string, zone: string): string {
  const locale = LOCALES[language] ?? LOCALES.en;
  if (value === null || value === undefined) return "";
  if (value instanceof Date && noDate(value)) return "";
  if (typeof value === "boolean") return language === "da" ? (value ? "Ja" : "Nej") : value ? "Yes" : "No";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(value).replace(".", locale.decimal);
  if (typeof value === "bigint") return value.toString();
  // A moment at midnight is a date with no time of day (a date question's answer, a
  // project's dates): the time is left out.
  if (value instanceof Date) return formatDate(value, isMidnight(value, zone) ? "d MMMM yyyy" : "d MMMM yyyy, HH:mm", zone, locale);
  if (Array.isArray(value)) return value.map((v) => printValue(v, language, zone)).join(", ");
  if (isSpan(value)) return formatDuration(value["@duration"], locale);
  if (typeof value === "object") return "";
  return String(value);
}

interface Scope {
  engine: Engine;
  values: Record<string, unknown>;
  /**
   * Inside a repeated section: which repetition, as "~0", "~1" (and "~0~2" inside one in
   * another). It ends the ID of everything printed there, so each printed block has an
   * ID of its own; the part before the first ~ is the layout's block.
   */
  suffix?: string;
  /** Inside a section repeated for each row of a list: that list's columns, so {{item.x}} prints as its column shows it. */
  item?: LabelColumn[];
}

class Worker {
  readonly errors: PreviewModel["errors"] = [];
  readonly hidden: PreviewModel["hidden"] = [];
  readonly language: string;
  readonly zone: string;
  readonly byId: Map<Id, Question>;
  readonly byKey: Map<string, Question>;

  constructor(
    readonly input: PreviewInput,
    readonly top: Scope,
    readonly itemEngine: Engine,
  ) {
    this.language = input.content.settings.language;
    this.zone = input.timezone ?? "Europe/Copenhagen";
    this.byId = new Map(questionsOf(input.content).map((q) => [q.id, q]));
    this.byKey = new Map(questionsOf(input.content).filter((q) => q.key).map((q) => [q.key as string, q]));
  }

  /** What's printed where a signature question isn't signed. */
  get unsigned(): string {
    return this.language === "da" ? "Ikke underskrevet" : "Not signed";
  }

  /** A signature question's answer as it prints, the time as other moments are; null when it isn't signed. */
  signature(raw: unknown): PrintedSignature | null {
    const signature = signed(raw);
    return signature && { name: signature.name, time: formatDate(signature.at, "d MMMM yyyy, HH:mm", this.zone, LOCALES[this.language] ?? LOCALES.en) };
  }

  run(scope: Scope, element: Id, expr: string): unknown {
    try {
      return scope.engine.evaluateRaw(expr, scope.values);
    } catch (error) {
      this.errors.push({ element, message: error instanceof ExpressionError ? error.message : String(error) });
      return undefined;
    }
  }

  /** What {{ expr }} prints: its value as text, or ⚠ when it fails or gives what can't be printed. */
  print(scope: Scope, element: Id, expr: string): string {
    const value = this.run(scope, element, expr);
    if (value === undefined) return "⚠";
    if (value instanceof Date && Number.isNaN(value.getTime())) {
      this.errors.push({ element, message: "This gives a date outside the years a report can print." });
      return "⚠";
    }
    try {
      // A name standing on its own prints as its question shows it (labels.ts).
      return printValue(shownAs(expr, plain(value), this.labels(scope)), this.language, this.zone);
    } catch (error) {
      this.errors.push({ element, message: error instanceof Error ? error.message : String(error) });
      return "⚠";
    }
  }

  /** What labels.ts needs to print a choice as its question shows it. */
  labels(scope: Scope): LabelContext {
    return { questions: this.byKey, item: scope.item, answer: (key) => plain((scope.values.answers as Record<string, unknown> | undefined)?.[key]) };
  }

  shows(scope: Scope, element: Id, rule: string | null | undefined): boolean {
    if (!rule?.trim()) return true;
    const result = this.run(scope, element, rule);
    return result === undefined ? true : result === true;
  }

  text(scope: Scope, element: Id, text: string): string {
    let out = "";
    let last = 0;
    for (const found of interpolations(text)) {
      out += text.slice(last, found.start);
      if (found.closed && found.expr) out += this.print(scope, element, found.expr);
      last = found.end;
    }
    return out + text.slice(last);
  }

  rich(scope: Scope, element: Id, doc: RichText | null | undefined): RichText | null {
    if (!doc) return null;
    const visit = (node: RichNode): RichNode[] => {
      if (node.type === "variable") {
        const text = this.print(scope, element, String(node.attrs?.expr ?? ""));
        return text ? [{ type: "text", text }] : [];
      }
      if (node.type === "text") {
        const text = this.text(scope, element, node.text ?? "");
        return text ? [{ ...node, text }] : [];
      }
      return [node.content ? { ...node, content: node.content.flatMap(visit) } : node];
    };
    return { type: "doc", content: doc.content.flatMap(visit) };
  }

  /** An answer as the PDF prints it. */
  answer(question: Question, raw: unknown): { text: string | null; rich: RichText | null; rows: Grid | null; signature?: PrintedSignature } {
    const s = settingsOf(question.type, question.settings);
    const locale = LOCALES[this.language] ?? LOCALES.en;
    const none = { text: null, rich: null, rows: null };
    if (raw === null || raw === undefined || raw === "") {
      if (question.type === "signature") return { ...none, text: this.unsigned };
      if (question.type !== "calculated") return { ...none, text: "" };
    }
    switch (question.type) {
      case "rich_text":
        return { ...none, rich: raw && typeof raw === "object" ? (raw as RichText) : { type: "doc", content: [{ type: "paragraph", content: raw ? [{ type: "text", text: String(raw) }] : [] }] } };
      case "number": {
        const n = Number(raw);
        const text = s.whole ? formatNumber(BigInt(Math.trunc(n)), 0, locale.decimal, locale.group) : formatNumber(n, Number(s.decimals ?? 1), locale.decimal, locale.group);
        return { ...none, text: s.unit ? `${text} ${s.unit}` : text };
      }
      case "datetime": {
        const date = new Date(String(raw));
        if (Number.isNaN(date.getTime())) return { ...none, text: "" };
        return { ...none, text: formatDate(date, s.mode === "date" ? "d MMMM yyyy" : "d MMMM yyyy, HH:mm", this.zone, locale) };
      }
      case "yes_no":
        return { ...none, text: raw ? String(s.yes_label) : String(s.no_label) };
      case "dropdown":
        return { ...none, text: (s.options as { value: string; label: string }[]).find((o) => o.value === raw)?.label ?? String(raw) };
      case "multi_select": {
        const options = s.options as { value: string; label: string }[];
        return { ...none, text: (Array.isArray(raw) ? raw : []).map((v) => options.find((o) => o.value === v)?.label ?? String(v)).join(", ") };
      }
      case "secret":
        return { ...none, text: printed(String(raw ?? ""), s.pdf as "partial" | "omit") };
      case "cvss": {
        const v = (raw ?? {}) as { vector?: string; score?: number; severity?: string };
        return { ...none, text: v.vector ? `${formatNumber(Number(v.score ?? 0), 1, locale.decimal, locale.group)} ${v.severity ?? ""} (${v.vector})` : "" };
      }
      case "repeating":
      case "table":
        return { ...none, rows: this.grid(question, null) };
      case "person":
        return { ...none, text: String((raw as { display_name?: unknown }).display_name ?? "") };
      case "signature": {
        const signature = this.signature(raw);
        return signature ? { ...none, signature } : { ...none, text: this.unsigned };
      }
      case "photo":
      case "file":
        return { ...none, text: Array.isArray(raw) ? `${raw.length} ${question.type === "photo" ? "photo" : "file"}${raw.length === 1 ? "" : "s"}` : "" };
      default:
        return { ...none, text: printValue(raw, this.language, this.zone) };
    }
  }

  cell(column: { type: string; settings?: Record<string, unknown> }, value: unknown): string {
    const s = settingsOf(column.type, column.settings ?? {});
    const locale = LOCALES[this.language] ?? LOCALES.en;
    if (value === null || value === undefined || value === "") return "";
    if (column.type === "dropdown") return (s.options as { value: string; label: string }[]).find((o) => o.value === value)?.label ?? String(value);
    if (column.type === "yes_no") return value ? String(s.yes_label) : String(s.no_label);
    if (column.type === "number" && typeof value === "number") {
      const text = s.whole ? formatNumber(BigInt(Math.trunc(value)), 0, locale.decimal, locale.group) : formatNumber(value, Number(s.decimals ?? 1), locale.decimal, locale.group);
      return s.unit ? `${text} ${s.unit}` : text;
    }
    if (column.type === "datetime") {
      const date = new Date(String(value));
      return Number.isNaN(date.getTime()) ? "" : formatDate(date, s.mode === "date" ? "d MMM yyyy" : "d MMM yyyy, HH:mm", this.zone, locale);
    }
    return String(value);
  }

  /** A repeating group's or table's rows as printed; with numbers, a first column counts them. */
  grid(question: Question, keys: string[] | null, numbers = false): Grid {
    const s = settingsOf(question.type, question.settings);
    type Col = { key: string; label: string; type: string; settings?: Record<string, unknown> };
    const all = s.columns as Col[];
    const columns = keys ? keys.map((k) => all.find((c) => c.key === k)).filter((c): c is Col => !!c) : all;
    const raw = this.input.answers[question.id];
    const rows = Array.isArray(raw) ? (raw as Record<string, unknown>[]) : [];
    const grid: Grid = question.type === "table"
      ? {
          headers: ["", ...columns.map((c) => c.label)],
          rows: (s.rows as { key: string; label: string }[]).map((row, i) => [row.label, ...columns.map((c) => this.cell(c, rows[i]?.[c.key]))]),
        }
      : { headers: columns.map((c) => c.label), rows: rows.map((row) => columns.map((c) => this.cell(c, row[c.key]))) };
    if (!numbers) return grid;
    return { headers: [this.language === "da" ? "Nr." : "No.", ...grid.headers], rows: grid.rows.map((row, i) => [String(i + 1), ...row]) };
  }

  blocks(scope: Scope, blocks: Block[], item: boolean): Shown[] {
    return blocks.flatMap((block) => this.block(scope, block, item));
  }

  block(scope: Scope, b: Block, item: boolean): Shown[] {
    if (b.kind === "section" && b.repeat_for?.trim()) {
      const list = this.run(scope, b.id, b.repeat_for);
      const items = Array.isArray(list) ? list : [];
      if (!items.length) this.hidden.push({ id: b.id, reason: "Repeated for each item, and there are none" });
      return items.flatMap((entry, i) => {
        // The item as the list gave it: its cells keep their kinds (see answerValue).
        const inner: Scope = { engine: this.itemEngine, values: { ...scope.values, item: new CelValue(entry) }, suffix: `${scope.suffix ?? ""}~${i}`,
          item: repeatedColumns(b.repeat_for, this.byKey) ?? scope.item };
        return this.section(inner, b, `${b.id}${inner.suffix}`, true);
      });
    }
    if (!this.shows(scope, b.id, b.visible_when)) {
      this.hidden.push({ id: b.id, reason: b.kind === "section" ? "Section hidden by its rule, with what's in it" : "Hidden by its rule" });
      return [];
    }
    const id = `${b.id}${scope.suffix ?? ""}`;
    switch (b.kind) {
      case "section":
        return this.section(scope, b, id, item);
      case "cover":
        return [{ kind: "cover", id, title: this.text(scope, id, b.title), subtitle: this.text(scope, id, b.subtitle),
          facts: b.facts.map((f) => ({ label: this.text(scope, id, f.label), value: this.text(scope, id, f.value) })).filter((f) => f.value), showLogo: b.show_logo }];
      case "toc":
        return [{ kind: "toc", id, title: this.text(scope, id, b.title), depth: b.depth }];
      case "heading":
        return [{ kind: "heading", id, text: this.text(scope, id, b.text) }];
      case "text":
        return [{ kind: "text", id, content: this.rich(scope, id, b.content) as RichText }];
      case "answer": {
        const q = b.question ? this.byId.get(b.question) : undefined;
        if (!q) return [];
        const raw = q.type === "calculated" ? scope.values.answers && (scope.values.answers as Record<string, unknown>)[q.key ?? ""] : this.input.answers[q.id];
        return [{ kind: "answer", id, label: b.show_label ? q.label : null, ...this.answer(q, raw) }];
      }
      case "table": {
        const q = b.question ? this.byId.get(b.question) : undefined;
        if (!q || !(q.type === "repeating" || q.type === "table")) return [];
        return [{ kind: "table", id, caption: this.text(scope, id, b.caption), grid: this.grid(q, b.columns, b.row_numbers ?? false), emptyText: this.text(scope, id, b.empty_text) }];
      }
      case "image": {
        const asset = b.source === "template" && b.asset ? this.input.assets[b.asset] : undefined;
        const photos = b.source === "question" && b.question ? this.input.answers[b.question] : undefined;
        const url = asset?.url ?? (Array.isArray(photos) && typeof photos[0] === "string" ? photos[0] : null);
        return [{ kind: "image", id, url, caption: this.text(scope, id, b.caption), width: b.width, ratio: asset ? asset.height / Math.max(1, asset.width) : 0.6 }];
      }
      case "gallery": {
        const photos = b.question ? this.input.answers[b.question] : undefined;
        return [{ kind: "gallery", id, urls: Array.isArray(photos) ? photos.filter((p): p is string => typeof p === "string") : [], caption: this.text(scope, id, b.caption), perRow: b.per_row }];
      }
      case "callout": {
        let tone = b.tone;
        if (b.tone_rule?.trim()) {
          const named = this.run(scope, id, b.tone_rule);
          if (typeof named === "string" && ["info", "note", "warning", "critical", "success"].includes(named)) tone = named as Tone;
        }
        return [{ kind: "callout", id, tone, colour: b.colour, title: this.text(scope, id, b.title), content: this.rich(scope, id, b.content) as RichText }];
      }
      case "severity_summary": {
        const q = b.question ? this.byId.get(b.question) : undefined;
        const raw = q ? this.input.answers[q.id] : undefined;
        const rows = Array.isArray(raw) ? (raw as Record<string, unknown>[]) : [];
        // A level is named as the column shows it ("Høj"); a dropdown keeps a value of
        // its own for each choice ("hoej"), so a row counts by either.
        const column = q ? (settingsOf(q.type, q.settings).columns as { key: string; type: string; settings?: Record<string, unknown> }[] | undefined)?.find((c) => c.key === b.column) : undefined;
        const shown = (row: Record<string, unknown>) => {
          const value = row[b.column ?? ""];
          return [String(value ?? ""), column ? this.cell(column, value) : ""].map((text) => text.trim().toLowerCase());
        };
        const counts = b.levels.map((level) => ({ level, count: rows.filter((r) => shown(r).includes(level.trim().toLowerCase())).length }));
        return [{ kind: "severity_summary", id, caption: this.text(scope, id, b.caption), counts }];
      }
      case "sources": {
        const items = [...b.items];
        const q = b.question ? this.byId.get(b.question) : undefined;
        const raw = q ? this.input.answers[q.id] : undefined;
        if (q && Array.isArray(raw)) {
          const [first, second] = (settingsOf(q.type, q.settings).columns as { key: string }[]).map((c) => c.key);
          const title = (q.settings.columns as { key: string }[]).some((c) => c.key === "title") ? "title" : first;
          const link = (q.settings.columns as { key: string }[]).some((c) => c.key === "link") ? "link" : second;
          for (const row of raw as Record<string, unknown>[]) if (row[title]) items.push({ title: String(row[title]), link: String(row[link] ?? "") });
        }
        return [{ kind: "sources", id, intro: this.text(scope, id, b.intro), items }];
      }
      case "signatures":
        return [{ kind: "signatures", id, layout: b.layout, showDate: b.show_date, signers: b.signers.map((s) => ({
          ...s, label: this.text(scope, id, s.label),
          // Signed in the form: what its signature question prints, or null while it isn't signed.
          ...(s.role === "pad" ? { signed: this.signature(s.question ? this.input.answers[s.question] : null) } : {}),
        })) }];
      case "columns":
        return [{ kind: "columns", id, columns: b.columns.map((column) => this.blocks(scope, column, item)) }];
      case "page_break":
        return [{ kind: "page_break", id }];
      case "switch":
        return this.blocks(scope, this.picked(scope, b), item);
    }
  }

  /** The blocks of the switch's case for these answers; the others say why they're left out. */
  picked(scope: Scope, b: Extract<Block, { kind: "switch" }>): Block[] {
    const value = b.value?.trim() ? plain(this.run(scope, b.id, b.value)) : undefined;
    const given = value === null || value === "" ? "nothing" : `“${String(value)}”`;
    const at = b.cases.findIndex((c) => c.match === value);
    const chosen = value === undefined ? null : at < 0 ? b.otherwise : b.cases[at].blocks;
    const reason = value === undefined ? "What picks the case can't be worked out" : `The answers give ${given}`;
    for (const list of [...b.cases.map((c) => c.blocks), b.otherwise]) {
      if (list !== chosen) for (const inner of list) this.hidden.push({ id: inner.id, reason });
    }
    return chosen ?? [];
  }

  section(scope: Scope, b: Extract<Block, { kind: "section" }>, id: Id, item: boolean): Shown[] {
    if (b.repeat_for?.trim() && !this.shows(scope, b.id, b.visible_when)) return [];
    return [{
      // Content the server hasn't normalised yet may leave these out: its defaults.
      kind: "section", id, title: this.text(scope, b.id, b.title), intro: this.rich(scope, b.id, b.intro), newPage: b.new_page ?? true,
      numbered: b.numbered ?? true, landscape: b.landscape ?? false, blocks: this.blocks(scope, b.blocks ?? [], item),
    }];
  }
}

/** Everything a template prints for these answers. */
export function preview(input: PreviewInput): PreviewModel {
  const { content } = input;
  const names = declarations(content, input.library?.names);
  const options: EngineOptions = { timezone: input.timezone, language: content.settings.language, tables: input.library?.tables };
  const engine = new Engine(names, options);
  const itemEngine = new Engine({ ...names, ...ITEM }, options);
  const questions = questionsOf(content);
  const answers: Record<string, unknown> = {};
  for (const q of questions) if (q.key && q.type !== "calculated") answers[q.key] = answerValue(q, input.answers[q.id]);
  const values: Record<string, unknown> = { ...input.context, ...(input.library?.values ?? {}), answers };
  const errors: PreviewModel["errors"] = [];
  // Calculated values, each kept as the kind of value it's declared to give. One that
  // gives another kind (a whole number that works out as 0.75) is its own question's
  // problem and stays empty, rather than failing every expression that reads the answers.
  const calculate = (report: boolean) => {
    for (const q of calculationOrder(questions, engine)) {
      const name = `answers.${q.key}`;
      const spec = engine.declarations.get(name);
      try {
        const value = engine.evaluateRaw(q.value ?? "", values);
        try {
          answers[q.key as string] = spec ? toCel(value, spec, name) : value;
        } catch {
          answers[q.key as string] = null;
          if (report) errors.push({ element: q.id, message: `This should give ${human(spec?.name ?? "")}, but with these answers it gives ${printValue(plain(value), content.settings.language, input.timezone ?? "Europe/Copenhagen") || "something else"}.` });
        }
      } catch (error) {
        if (report) errors.push({ element: q.id, message: error instanceof ExpressionError ? error.message : String(error) });
      }
    }
  };
  // What a question starts as may read a calculated value, and a calculated value what
  // a question starts as: the calculated values are worked out, then the start values
  // (in the form's order), then the calculated values again.
  const starting = questions.filter((q) => q.key && q.type !== "calculated" && q.default?.trim() && input.answers[q.id] === undefined);
  if (starting.length) calculate(false);
  // A question not answered yet starts as its rule says (one cleared on purpose is kept
  // as null, and stays empty).
  const defaults: PreviewModel["defaults"] = {};
  for (const q of starting) {
    try {
      const start = startValue(q, plain(engine.evaluateRaw(q.default as string, values)), input.timezone ?? "Europe/Copenhagen");
      if (start === null) continue;
      defaults[q.id] = start;
      answers[q.key as string] = answerValue(q, start);
    } catch (error) {
      errors.push({ element: q.id, message: error instanceof ExpressionError ? error.message : String(error) });
    }
  }
  calculate(true);
  // Blocks that print an answer as it's kept (an Answer block, a table) read what a
  // question starts as too, as text and rules do.
  const worker = new Worker({ ...input, answers: { ...input.answers, ...defaults } }, { engine, values }, itemEngine);
  worker.errors.push(...errors);
  const blocks = worker.blocks({ engine, values }, content.layout, false);

  // The form, for "Try it": what it hides, what it requires, what fails its check.
  const scope = { engine, values };
  const formHidden: Id[] = [];
  const formRequired: Id[] = [];
  const invalid: PreviewModel["invalid"] = [];
  for (const step of content.form) {
    if (!worker.shows(scope, step.id, step.visible_when)) formHidden.push(step.id);
    for (const q of step.questions) {
      if (!worker.shows(scope, q.id, q.visible_when)) formHidden.push(q.id);
      const required = q.required_when?.trim() ? worker.run(scope, q.id, q.required_when) === true : q.required;
      if (required && fieldType(q.type).asks) formRequired.push(q.id);
      if (q.valid_when?.trim() && worker.run(scope, q.id, q.valid_when) === false) invalid.push({ id: q.id, message: q.valid_message || "This answer isn't valid." });
    }
  }
  // The style's text elements read the context and the library alone; the server
  // checks them when the style is saved, so one that fails here prints empty.
  const pageTexts: Record<string, string> = {};
  const counted = worker.errors.length;
  for (const [key, text] of Object.entries(input.pageTexts ?? {})) pageTexts[key] = worker.text(scope, key, text);
  worker.errors.splice(counted);
  return {
    blocks,
    hidden: worker.hidden,
    errors: worker.errors,
    values: plain(answers) as Record<string, unknown>,
    defaults,
    formHidden,
    formRequired,
    invalid,
    pageTexts,
  };
}
