// Whether a template makes sense: the builder's live copy of
// backend/app/templates/checks.py, run as the designer types. The server's verdict
// decides whether a draft can be published; shared/templates/checks.json holds both
// to the same problems in the same words and order: steps and their questions, then
// loops among calculated values, then the layout, depth first.

import { RE2JS } from "re2js";
import { Engine, ExpressionError, human, unknownName } from "#lib/cel/engine.js";
import { fieldType, settingsOf } from "./fields";
import { declarations, ITEM, questionNames } from "./names";
import { docExpressions, interpolations } from "./text";
import { questionsOf, type Block, type Problem, type Question, type RichText, type TemplateContent } from "./types";

// Words CEL keeps for itself: answers.<key> can't be read with one of them as key.
export const RESERVED = new Set([
  "true", "false", "null", "in", "as", "break", "const", "continue", "else", "for", "function", "if",
  "import", "let", "loop", "package", "namespace", "return", "var", "void", "while",
]);
const LISTS = new Set(["repeating", "table"]);
export const ITEM_OUTSIDE = "item is only there inside a section repeated for each item.";

const fits = (got: string, expected: string) =>
  got === "dyn" || got === expected || (expected === "list" && got.startsWith("list<"));

type Columns = { key: string }[];

export interface CheckOptions {
  library?: Record<string, string>;
  assets?: Iterable<string>;
  timezone?: string;
}

class Checker {
  readonly problems: Problem[] = [];
  readonly seenIds = new Set<string>();
  readonly byId: Map<string, Question>;
  readonly assets: Set<string>;

  constructor(
    readonly content: TemplateContent,
    readonly engine: Engine,
    readonly itemEngine: Engine,
    assets: Iterable<string>,
  ) {
    this.byId = new Map(questionsOf(content).map((q) => [q.id, q]));
    this.assets = new Set(assets);
  }

  add(element: string, field: string, message: string) {
    this.problems.push({ element, field, message });
  }

  id(element: string) {
    if (this.seenIds.has(element)) this.add(element, "id", `Another element already uses the ID ${element}.`);
    this.seenIds.add(element);
  }

  message(error: ExpressionError, item: boolean): string {
    return !item && error.message === unknownName("item") ? ITEM_OUTSIDE : error.message;
  }

  /** An expression that, when set, must work and give the expected type. */
  expr(element: string, field: string, expr: string | null | undefined, expected: string | null, item = false) {
    if (expr === null || expr === undefined) return;
    if (!expr.trim()) {
      this.add(element, field, "Write the expression, or remove the rule.");
      return;
    }
    let got: string;
    try {
      got = (item ? this.itemEngine : this.engine).check(expr);
    } catch (error) {
      if (!(error instanceof ExpressionError)) throw error;
      this.add(element, field, this.message(error, item));
      return;
    }
    if (expected !== null && !fits(got, expected)) {
      this.add(element, field, `This should give ${human(expected)}, but gives ${human(got)}.`);
    }
  }

  /** An expression whose value is printed: anything but a list or a map. */
  printed(element: string, field: string, expr: string, item: boolean) {
    if (!expr) {
      this.add(element, field, "Write an expression between {{ and }}.");
      return;
    }
    let got: string;
    try {
      got = (item ? this.itemEngine : this.engine).check(expr);
    } catch (error) {
      if (!(error instanceof ExpressionError)) throw error;
      this.add(element, field, this.message(error, item));
      return;
    }
    if (got.startsWith("list") || got.startsWith("map")) {
      this.add(element, field, 'This gives a list or a map, which can\'t be printed as it is: pick one item, or join a list of text with .join(", ").');
    }
  }

  text(element: string, field: string, text: string, item: boolean) {
    for (const found of interpolations(text)) {
      if (!found.closed) this.add(element, field, "A {{ has no closing }}.");
      else this.printed(element, field, found.expr, item);
    }
  }

  rich(element: string, field: string, doc: RichText | null, item: boolean) {
    if (doc === null) return;
    for (const expr of docExpressions(doc)) this.printed(element, field, expr.trim(), item);
  }

  // The form

  question(q: Question, seenKeys: Set<string>) {
    this.id(q.id);
    const type = fieldType(q.type);
    if (type.asks) {
      if (q.key === null) this.add(q.id, "key", "Give the question a variable name.");
      else if (RESERVED.has(q.key)) this.add(q.id, "key", `${q.key} is a reserved word in expressions: choose another variable name.`);
      else if (seenKeys.has(q.key)) this.add(q.id, "key", `Another question already uses the variable name ${q.key}.`);
      if (q.key !== null) seenKeys.add(q.key);
    }
    this.settings(q);
    this.expr(q.id, "required_when", q.required_when, "bool");
    this.expr(q.id, "visible_when", q.visible_when, "bool");
    this.expr(q.id, "valid_when", q.valid_when, "bool");
    const own = q.key ? questionNames(q)[`answers.${q.key}`] : undefined;
    if (q.default !== null && q.default !== undefined) {
      if (own === undefined || q.type === "calculated") this.add(q.id, "default", "This kind of question can't have a default.");
      else this.expr(q.id, "default", q.default, own);
    }
    if (q.type === "calculated") {
      if (!(q.value ?? "").trim()) this.add(q.id, "value", "Write the expression that works out this value.");
      else this.expr(q.id, "value", q.value, own ?? null);
    } else if (q.value !== null && q.value !== undefined) {
      this.add(q.id, "value", "Only calculated values have an expression.");
    }
  }

  settings(q: Question) {
    const s = settingsOf(q.type, q.settings);
    if ((q.type === "text" || q.type === "serial") && s.pattern) {
      try {
        RE2JS.compile(String(s.pattern));
      } catch {
        this.add(q.id, "settings.pattern", "This pattern isn't a regular expression Skjald can use (RE2 syntax).");
      }
    }
    if (q.type === "number" && s.min !== null && s.max !== null && Number(s.min) > Number(s.max)) {
      this.add(q.id, "settings.min", "The smallest value is larger than the largest.");
    }
    if (q.type === "multi_select" && s.min_selected !== null && s.max_selected !== null && Number(s.min_selected) > Number(s.max_selected)) {
      this.add(q.id, "settings.min_selected", "The fewest choices are more than the most.");
    }
    const duplicates = (keys: string[]) => [...new Set(keys.filter((k, i) => keys.indexOf(k) !== i))].sort();
    if (LISTS.has(q.type)) {
      for (const key of duplicates((s.columns as Columns).map((c) => c.key))) {
        this.add(q.id, "settings.columns", `Two columns use the variable name ${key}.`);
      }
    }
    if (q.type === "table") {
      for (const key of duplicates((s.rows as Columns).map((r) => r.key))) {
        this.add(q.id, "settings.rows", `Two rows use the variable name ${key}.`);
      }
    }
    if (q.type === "repeating" && Number(s.min_rows) > Number(s.max_rows)) {
      this.add(q.id, "settings.min_rows", "The fewest rows are more than the most.");
    }
  }

  /** Calculated values that depend on themselves, through others or directly. */
  loops() {
    const calculated = new Map(
      questionsOf(this.content)
        .filter((q) => q.type === "calculated" && q.key && (q.value ?? "").trim())
        .map((q) => [q.key as string, q]),
    );
    const depends = new Map<string, string[]>();
    for (const [key, q] of calculated) {
      let read: string[] = [];
      try {
        read = this.engine.references(q.value ?? "");
      } catch {
        read = [];
      }
      const keys = read.filter((n) => n.startsWith("answers.")).map((n) => n.split(".")[1]).filter((k) => calculated.has(k));
      depends.set(key, [...new Set(keys)].sort());
    }
    for (const [key, q] of calculated) {
      const path = pathBack(key, depends);
      if (path.length) this.add(q.id, "value", `This value depends on itself: ${[key, ...path].join(" → ")}.`);
    }
  }

  // The layout

  chosen(element: string, questionId: string | null, missing: string): Question | null {
    if (questionId === null) {
      this.add(element, "question", missing);
      return null;
    }
    const found = this.byId.get(questionId) ?? null;
    if (found === null) this.add(element, "question", "The question this block prints was removed.");
    return found;
  }

  isList(element: string, q: Question): boolean {
    if (!LISTS.has(q.type)) {
      this.add(element, "question", `“${q.label}” isn't a repeating group or table.`);
      return false;
    }
    return true;
  }

  column(element: string, field: string, q: Question, key: string) {
    const columns = settingsOf(q.type, q.settings).columns as Columns;
    if (!columns.some((c) => c.key === key)) this.add(element, field, `“${q.label}” has no column ${key}.`);
  }

  block(b: Block, outer: boolean) {
    this.id(b.id);
    // A repeated section's own rule, title and intro are worked out for each item;
    // what it repeats for, outside them.
    const item = outer || (b.kind === "section" && b.repeat_for !== null && b.repeat_for !== undefined);
    this.expr(b.id, "visible_when", b.visible_when, "bool", item);
    switch (b.kind) {
      case "cover":
        this.text(b.id, "title", b.title, item);
        this.text(b.id, "subtitle", b.subtitle, item);
        b.facts.forEach((fact, i) => {
          this.text(b.id, `facts.${i}.label`, fact.label, item);
          this.text(b.id, `facts.${i}.value`, fact.value, item);
        });
        break;
      case "toc":
        this.text(b.id, "title", b.title, item);
        break;
      case "section":
        this.text(b.id, "title", b.title, item);
        this.rich(b.id, "intro", b.intro ?? null, item);
        this.expr(b.id, "repeat_for", b.repeat_for, "list", outer);
        for (const child of b.blocks) this.block(child, item);
        break;
      case "heading":
        this.text(b.id, "text", b.text, item);
        break;
      case "text":
        this.rich(b.id, "content", b.content, item);
        break;
      case "answer": {
        const q = this.chosen(b.id, b.question, "Choose the question to print.");
        if (q !== null && !fieldType(q.type).asks) this.add(b.id, "question", "Headings have no answer to print.");
        break;
      }
      case "table": {
        const q = this.chosen(b.id, b.question, "Choose the repeating group or table to print.");
        if (q !== null && this.isList(b.id, q)) for (const key of b.columns ?? []) this.column(b.id, "columns", q, key);
        this.text(b.id, "caption", b.caption, item);
        this.text(b.id, "empty_text", b.empty_text, item);
        break;
      }
      case "image":
        if (b.source === "template") {
          if (b.asset === null) this.add(b.id, "asset", "Choose an image.");
          else if (!this.assets.has(b.asset)) this.add(b.id, "asset", "The image file is missing: upload it again.");
        } else {
          const q = this.chosen(b.id, b.question, "Choose the photo question.");
          if (q !== null && q.type !== "photo") this.add(b.id, "question", `“${q.label}” isn't a photo question.`);
        }
        this.text(b.id, "caption", b.caption, item);
        break;
      case "gallery": {
        const q = this.chosen(b.id, b.question, "Choose the photo question.");
        if (q !== null) {
          if (q.type !== "photo") this.add(b.id, "question", `“${q.label}” isn't a photo question.`);
          else if (!settingsOf(q.type, q.settings).multiple) {
            this.add(b.id, "question", `“${q.label}” takes one photo: let it take several to show a gallery.`);
          }
        }
        this.text(b.id, "caption", b.caption, item);
        break;
      }
      case "callout":
        this.expr(b.id, "tone_rule", b.tone_rule, "string", item);
        if (b.tone === "custom" && b.colour === null) this.add(b.id, "colour", "Choose the custom colour.");
        this.text(b.id, "title", b.title, item);
        this.rich(b.id, "content", b.content, item);
        break;
      case "severity_summary": {
        const q = this.chosen(b.id, b.question, "Choose the repeating group to count.");
        if (q !== null && this.isList(b.id, q)) {
          if (b.column === null) this.add(b.id, "column", "Choose the column that holds each row's severity.");
          else this.column(b.id, "column", q, b.column);
        }
        this.text(b.id, "caption", b.caption, item);
        break;
      }
      case "sources":
        this.text(b.id, "intro", b.intro, item);
        if (b.question !== null) {
          const q = this.chosen(b.id, b.question, "");
          if (q !== null) this.isList(b.id, q);
        }
        break;
      case "signatures":
        b.signers.forEach((signer, i) => this.text(b.id, `signers.${i}.label`, signer.label, item));
        break;
      case "columns":
        for (const column of b.columns) for (const child of column) this.block(child, item);
        break;
      case "page_break":
        break;
    }
  }
}

/** The shortest way from start back to itself, if there is one. */
function pathBack(start: string, depends: Map<string, string[]>): string[] {
  const queue: string[][] = (depends.get(start) ?? []).map((d) => [d]);
  const visited = new Set<string>();
  while (queue.length) {
    const path = queue.shift() as string[];
    const last = path[path.length - 1];
    if (last === start) return path;
    if (visited.has(last)) continue;
    visited.add(last);
    for (const d of depends.get(last) ?? []) queue.push([...path, d]);
  }
  return [];
}

/** Every problem in the template, in the order the builder shows them. */
export function check(content: TemplateContent, options: CheckOptions = {}): Problem[] {
  const names = declarations(content, options.library);
  const engineOptions = { timezone: options.timezone, language: content.settings.language };
  const checker = new Checker(
    content,
    new Engine(names, engineOptions),
    new Engine({ ...names, ...ITEM }, engineOptions),
    options.assets ?? [],
  );
  const seenKeys = new Set<string>();
  for (const step of content.form) {
    checker.id(step.id);
    checker.expr(step.id, "visible_when", step.visible_when, "bool");
    for (const q of step.questions) checker.question(q, seenKeys);
  }
  checker.loops();
  for (const b of content.layout) checker.block(b, false);
  return checker.problems;
}
