// What a template prints for a set of answers: every block worked out (rules, text
// with {{ }} expressions, repeated sections, tables, numbers), ready to be split into
// pages (pages.ts) and drawn. The builder's Layout tab and "Try it" use it with sample
// answers; it runs in the expression worker, which stops it if it takes too long.
// Phase 3's renderer does the same work on the server for the real PDF.

import { Engine, ExpressionError, plain, type EngineOptions } from "#lib/cel/engine.js";
import { formatDate } from "#lib/cel/dates.js";
import { LOCALES, type Table as LookupTable } from "#lib/cel/library.js";
import { formatNumber } from "#lib/cel/numbers.js";
import { fieldType, settingsOf } from "./fields";
import { CONTEXT_GROUPS, declarations, ITEM } from "./names";
import { printed } from "./secrets";
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
  | { kind: "answer"; id: Id; label: string | null; text: string | null; rich: RichText | null; rows: Grid | null }
  | { kind: "table"; id: Id; caption: string; grid: Grid; emptyText: string }
  | { kind: "image"; id: Id; url: string | null; caption: string; width: string; ratio: number }
  | { kind: "gallery"; id: Id; urls: string[]; caption: string; perRow: number }
  | { kind: "callout"; id: Id; tone: Tone; colour: string | null; title: string; content: RichText }
  | { kind: "severity_summary"; id: Id; caption: string; counts: { level: string; count: number }[] }
  | { kind: "sources"; id: Id; intro: string; items: { title: string; link: string }[] }
  | { kind: "signatures"; id: Id; signers: Signer[]; layout: "row" | "stack"; showDate: boolean }
  | { kind: "columns"; id: Id; columns: Shown[][] }
  | { kind: "page_break"; id: Id };

export interface Grid {
  headers: string[];
  rows: string[][];
}

export interface PreviewModel {
  blocks: Shown[];
  /** Blocks left out, and why, for the builder to say. */
  hidden: { id: Id; reason: string }[];
  /** Expressions that failed, by element. */
  errors: { element: Id; message: string }[];
  /** The values expressions read: answers by variable name, calculated ones included. */
  values: Record<string, unknown>;
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

// Answers as expressions read them

/** One answer as expressions see it: a secret only as it prints, a photo only whether there is one. */
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
    case "signature":
      return { filled: Boolean(raw) };
    case "cvss": {
      const value = (raw ?? {}) as { vector?: string; score?: number; severity?: string };
      return { vector: value.vector ?? "", score: Number(value.score ?? 0), severity: value.severity ?? "" };
    }
    case "number":
      if (typeof raw !== "number") return null;
      return settings.whole ? Math.trunc(raw) : raw;
    default:
      return raw ?? null;
  }
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

function printValue(value: unknown, language: string, zone: string): string {
  const locale = LOCALES[language] ?? LOCALES.en;
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return language === "da" ? (value ? "Ja" : "Nej") : value ? "Yes" : "No";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(value).replace(".", locale.decimal);
  if (typeof value === "bigint") return value.toString();
  if (value instanceof Date) return formatDate(value, "d MMMM yyyy, HH:mm", zone, locale);
  if (Array.isArray(value)) return value.map((v) => printValue(v, language, zone)).join(", ");
  if (typeof value === "object") return "";
  return String(value);
}

interface Scope {
  engine: Engine;
  values: Record<string, unknown>;
}

class Worker {
  readonly errors: PreviewModel["errors"] = [];
  readonly hidden: PreviewModel["hidden"] = [];
  readonly language: string;
  readonly zone: string;
  readonly byId: Map<Id, Question>;

  constructor(
    readonly input: PreviewInput,
    readonly top: Scope,
    readonly itemEngine: Engine,
  ) {
    this.language = input.content.settings.language;
    this.zone = input.timezone ?? "Europe/Copenhagen";
    this.byId = new Map(questionsOf(input.content).map((q) => [q.id, q]));
  }

  run(scope: Scope, element: Id, expr: string): unknown {
    try {
      return scope.engine.evaluateRaw(expr, scope.values);
    } catch (error) {
      this.errors.push({ element, message: error instanceof ExpressionError ? error.message : String(error) });
      return undefined;
    }
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
      if (found.closed && found.expr) {
        const value = this.run(scope, element, found.expr);
        out += value === undefined ? "⚠" : printValue(plain(value), this.language, this.zone);
      }
      last = found.end;
    }
    return out + text.slice(last);
  }

  rich(scope: Scope, element: Id, doc: RichText | null | undefined): RichText | null {
    if (!doc) return null;
    const visit = (node: RichNode): RichNode[] => {
      if (node.type === "variable") {
        const value = this.run(scope, element, String(node.attrs?.expr ?? ""));
        const text = value === undefined ? "⚠" : printValue(plain(value), this.language, this.zone);
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
  answer(question: Question, raw: unknown): { text: string | null; rich: RichText | null; rows: Grid | null } {
    const s = settingsOf(question.type, question.settings);
    const locale = LOCALES[this.language] ?? LOCALES.en;
    const none = { text: null, rich: null, rows: null };
    if (raw === null || raw === undefined || raw === "") {
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
      case "photo":
      case "file":
      case "signature":
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
      return s.whole ? formatNumber(BigInt(Math.trunc(value)), 0, locale.decimal, locale.group) : formatNumber(value, Number(s.decimals ?? 1), locale.decimal, locale.group);
    }
    if (column.type === "datetime") {
      const date = new Date(String(value));
      return Number.isNaN(date.getTime()) ? "" : formatDate(date, "d MMM yyyy, HH:mm", this.zone, locale);
    }
    return String(value);
  }

  grid(question: Question, keys: string[] | null): Grid {
    const s = settingsOf(question.type, question.settings);
    type Col = { key: string; label: string; type: string; settings?: Record<string, unknown> };
    const all = s.columns as Col[];
    const columns = keys ? keys.map((k) => all.find((c) => c.key === k)).filter((c): c is Col => !!c) : all;
    const raw = this.input.answers[question.id];
    const rows = Array.isArray(raw) ? (raw as Record<string, unknown>[]) : [];
    if (question.type === "table") {
      const fixed = s.rows as { key: string; label: string }[];
      return {
        headers: ["", ...columns.map((c) => c.label)],
        rows: fixed.map((row, i) => [row.label, ...columns.map((c) => this.cell(c, rows[i]?.[c.key]))]),
      };
    }
    return { headers: columns.map((c) => c.label), rows: rows.map((row) => columns.map((c) => this.cell(c, row[c.key]))) };
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
        const inner: Scope = { engine: this.itemEngine, values: { ...scope.values, item: entry } };
        return this.section(inner, b, `${b.id}~${i}`, true);
      });
    }
    if (!this.shows(scope, b.id, b.visible_when)) {
      this.hidden.push({ id: b.id, reason: b.kind === "section" ? "Section hidden by its rule, with what's in it" : "Hidden by its rule" });
      return [];
    }
    const id = b.id;
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
        return [{ kind: "table", id, caption: this.text(scope, id, b.caption), grid: this.grid(q, b.columns), emptyText: this.text(scope, id, b.empty_text) }];
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
        const counts = b.levels.map((level) => ({ level, count: rows.filter((r) => String(r[b.column ?? ""] ?? "").toLowerCase() === level.toLowerCase()).length }));
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
        return [{ kind: "signatures", id, signers: b.signers.map((s) => ({ ...s, label: this.text(scope, id, s.label) })), layout: b.layout, showDate: b.show_date }];
      case "columns":
        return [{ kind: "columns", id, columns: b.columns.map((column) => this.blocks(scope, column, item)) }];
      case "page_break":
        return [{ kind: "page_break", id }];
    }
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
  for (const q of calculationOrder(questions, engine)) {
    try {
      answers[q.key as string] = engine.evaluateRaw(q.value ?? "", values);
    } catch (error) {
      errors.push({ element: q.id, message: error instanceof ExpressionError ? error.message : String(error) });
    }
  }
  const worker = new Worker(input, { engine, values }, itemEngine);
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
    formHidden,
    formRequired,
    invalid,
    pageTexts,
  };
}
