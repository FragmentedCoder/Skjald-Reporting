// Changes the builder makes to a template's content, as plain functions: new
// questions and blocks, renaming a variable everywhere it's read, and where a
// question is used.

import { renameReference, references, tokenize } from "#lib/cel/lexer.js";
import { fieldType } from "./fields";
import { interpolations } from "./text";
import { blocksOf, questionsOf, type Block, type Question, type RichNode, type RichText, type Step, type TemplateContent } from "./types";

/** A new ID such as q_k3x9w2pa: the prefix says what it names (s step, q question, b block). */
export function newId(prefix: "s" | "q" | "b"): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  return `${prefix}_${Array.from(bytes, (b) => "abcdefghijklmnopqrstuvwxyz0123456789"[b % 36]).join("")}`;
}

/** A variable name not taken yet: base, or base_2, base_3 and so on. */
export function freeKey(base: string, taken: Iterable<string | null>): string {
  const used = new Set(taken);
  if (!used.has(base)) return base;
  for (let n = 2; ; n++) if (!used.has(`${base}_${n}`)) return `${base}_${n}`;
}

/** A variable name made from a label: "Highest CVSS score" becomes highest_cvss_score. */
export function keyFrom(label: string): string {
  const slug = label
    .replace(/[æÆ]/g, "ae")
    .replace(/[øØ]/g, "oe")
    .replace(/[åÅ]/g, "aa")
    .normalize("NFKD")
    .replace(/[^\w\s]/g, "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/^[^a-z]+/, "")
    .slice(0, 50)
    .replace(/_+$/, "");
  return slug || "answer";
}

export const KEY_PATTERN = /^[a-z][a-z0-9_]{0,49}$/;

export function newQuestion(type: string, content: TemplateContent): Question {
  const field = fieldType(type);
  const label = type === "heading" ? "New part" : `New ${field.label.toLowerCase()} question`;
  return {
    id: newId("q"),
    key: field.asks ? freeKey(type, questionsOf(content).map((q) => q.key)) : null,
    type,
    label,
    help: "",
    required: false,
    required_when: null,
    visible_when: null,
    default: null,
    valid_when: null,
    valid_message: "",
    value: type === "calculated" ? "" : null,
    settings: field.settings(),
  };
}

export function newStep(): Step {
  return { id: newId("s"), title: "New step", help: "", visible_when: null, questions: [] };
}

// Every expression in a template

/** The same text with each {{ expression }} passed through change. */
function mapText(text: string, change: (expr: string) => string): string {
  let out = "";
  let last = 0;
  for (const found of interpolations(text)) {
    if (!found.closed) continue;
    out += text.slice(last, found.start) + `{{${change(found.expr)}}}`;
    last = found.end;
  }
  return out + text.slice(last);
}

function mapRich(doc: RichText | null | undefined, change: (expr: string) => string): RichText | null {
  if (!doc) return null;
  const visit = (node: RichNode): RichNode => {
    if (node.type === "variable") return { ...node, attrs: { ...node.attrs, expr: change(String(node.attrs?.expr ?? "")) } };
    if (node.type === "text") return { ...node, text: mapText(node.text ?? "", change) };
    return node.content ? { ...node, content: node.content.map(visit) } : node;
  };
  return { ...doc, content: doc.content.map(visit) };
}

// Content the server hasn't normalised yet may leave optional parts out.
const rule = (expr: string | null | undefined, change: (expr: string) => string) => (expr === null || expr === undefined ? null : change(expr));

function mapBlock(block: Block, change: (expr: string) => string): Block {
  const base = { ...block, visible_when: rule(block.visible_when, change) } as Block;
  const text = (value: string) => mapText(value, change);
  switch (base.kind) {
    case "cover":
      return { ...base, title: text(base.title), subtitle: text(base.subtitle), facts: base.facts.map((f) => ({ label: text(f.label), value: text(f.value) })) };
    case "toc":
      return { ...base, title: text(base.title) };
    case "section":
      return { ...base, title: text(base.title), intro: mapRich(base.intro, change), repeat_for: rule(base.repeat_for, change), blocks: base.blocks.map((b) => mapBlock(b, change)) };
    case "heading":
      return { ...base, text: text(base.text) };
    case "text":
      return { ...base, content: mapRich(base.content, change) as RichText };
    case "table":
      return { ...base, caption: text(base.caption), empty_text: text(base.empty_text) };
    case "image":
    case "gallery":
    case "severity_summary":
      return { ...base, caption: text(base.caption) };
    case "callout":
      return { ...base, tone_rule: rule(base.tone_rule, change), title: text(base.title), content: mapRich(base.content, change) as RichText };
    case "sources":
      return { ...base, intro: text(base.intro) };
    case "signatures":
      return { ...base, signers: base.signers.map((s) => ({ ...s, label: text(s.label) })) };
    case "columns":
      return { ...base, columns: base.columns.map((column) => column.map((b) => mapBlock(b, change))) };
    default:
      return base;
  }
}

/** The content with every expression in it passed through change. */
export function mapExpressions(content: TemplateContent, change: (expr: string) => string): TemplateContent {
  return {
    ...content,
    form: content.form.map((step) => ({
      ...step,
      visible_when: rule(step.visible_when, change),
      questions: step.questions.map((q) => ({
        ...q,
        required_when: rule(q.required_when, change),
        visible_when: rule(q.visible_when, change),
        default: rule(q.default, change),
        valid_when: rule(q.valid_when, change),
        value: rule(q.value, change),
      })),
    })),
    layout: content.layout.map((b) => mapBlock(b, change)),
  };
}

/** Every expression in the content, with where it is. */
export function expressionsOf(content: TemplateContent): string[] {
  const found: string[] = [];
  mapExpressions(content, (expr) => {
    found.push(expr);
    return expr;
  });
  return found;
}

/**
 * A question's variable name changed everywhere it's read: rules, calculated values,
 * text. Text inside quotes is never touched. Expressions that can't be read as CEL are
 * left as they are.
 */
export function renameKey(content: TemplateContent, from: string, to: string): TemplateContent {
  const renamed = mapExpressions(content, (expr) => {
    try {
      return renameReference(expr, `answers.${from}`, `answers.${to}`);
    } catch {
      return expr;
    }
  });
  return {
    ...renamed,
    form: renamed.form.map((step) => ({
      ...step,
      questions: step.questions.map((q) => (q.key === from ? { ...q, key: to } : q)),
    })),
  };
}

export interface Usage {
  /** Blocks that print the question. */
  blocks: Block[];
  /** How many expressions read it. */
  expressions: number;
}

/** Where a question is used: the blocks that print it and the expressions that read it. */
export function usage(content: TemplateContent, question: Question): Usage {
  const blocks = blocksOf(content.layout).filter((b) => "question" in b && b.question === question.id);
  let expressions = 0;
  if (question.key) {
    const prefix = `answers.${question.key}`;
    for (const expr of expressionsOf(content)) {
      try {
        const read = references(tokenize(expr), new Set([prefix, ...Object.keys(fieldType(question.type).names({})).map((s) => prefix + s)]));
        if (read.length) expressions += 1;
      } catch {
        // An expression that can't be read uses nothing.
      }
    }
  }
  return { blocks, expressions };
}
