// Expressions written inside {{ }} in plain text, and those in rich text: the
// browser's copy of the matching parts of backend/app/templates/text.py.

import type { RichNode, RichText } from "./types";

// What isn't seen at either end of a text: spaces of every kind, line breaks, the old
// separator controls, and marks with no width (a byte order mark, a zero-width space).
// JavaScript's trim() and Python's strip() don't take the same ones, so both sides use
// this list (backend/app/templates/text.py).
const UNSEEN = "\\t\\n\\v\\f\\r \\x1c-\\x1f\\x85\\xa0\\u1680\\u2000-\\u200d\\u2028\\u2029\\u202f\\u205f\\u2060\\u3000\\ufeff";
const ENDS = new RegExp(`^[${UNSEEN}]+|[${UNSEEN}]+$`, "g");

/** The text without what isn't seen at either end. */
export const trimmed = (text: string) => text.replace(ENDS, "");

/** Whether there's nothing to see in the text. */
export const blank = (text: string) => !trimmed(text);

export interface Interpolation {
  start: number;
  end: number;
  expr: string;
  closed: boolean;
}

/**
 * Each {{ expression }} in the text. An expression ends at the first }} outside
 * quotes and outside braces of its own, so a map such as {"a": {"b": 1}} fits.
 */
export function interpolations(text: string): Interpolation[] {
  const found: Interpolation[] = [];
  let i = 0;
  for (;;) {
    const start = text.indexOf("{{", i);
    if (start < 0) break;
    let j = start + 2;
    let depth = 0;
    let quote: string | null = null;
    let end = -1;
    while (j < text.length) {
      const c = text[j];
      if (quote !== null) {
        if (c === "\\") {
          j += 2;
          continue;
        }
        if (text.startsWith(quote, j)) {
          j += quote.length;
          quote = null;
          continue;
        }
        j += 1;
        continue;
      }
      if (c === "'" || c === '"') {
        quote = text.startsWith(c.repeat(3), j) ? c.repeat(3) : c;
        j += quote.length;
        continue;
      }
      if (c === "{") {
        depth += 1;
      } else if (c === "}") {
        if (depth === 0 && text.startsWith("}}", j)) {
          end = j;
          break;
        }
        depth = Math.max(depth - 1, 0);
      }
      j += 1;
    }
    if (end < 0) {
      found.push({ start, end: text.length, expr: trimmed(text.slice(start + 2)), closed: false });
      break;
    }
    found.push({ start, end: end + 2, expr: trimmed(text.slice(start + 2, end)), closed: true });
    i = end + 2;
  }
  return found;
}

/**
 * What's typed in a box to try expressions: an expression as rules have it, the same
 * in {{ }} as the name lists show it, or text with names in {{ }} as a text block has.
 */
export function readTyped(typed: string): { expr: string } | { text: string; parts: Interpolation[] } | { unclosed: true } {
  const parts = interpolations(typed);
  if (!parts.length) return { expr: typed.trim() };
  if (parts.some((p) => !p.closed)) return { unclosed: true };
  const [first] = parts;
  const alone = parts.length === 1 && !typed.slice(0, first.start).trim() && !typed.slice(first.end).trim();
  return alone ? { expr: first.expr } : { text: typed, parts };
}

function* nodes(node: RichNode | RichText): Generator<RichNode | RichText> {
  yield node;
  for (const child of node.content ?? []) yield* nodes(child);
}

/** The expressions in a document: its variables', then those in {{ }} in its text. */
export function docExpressions(doc: RichText): string[] {
  const found: string[] = [];
  for (const node of nodes(doc)) {
    if (node.type === "variable") found.push(String((node as RichNode).attrs?.expr ?? ""));
    else if (node.type === "text") found.push(...interpolations((node as RichNode).text ?? "").map((i) => i.expr));
  }
  return found;
}

/** The document's words, paragraphs on their own lines, for expressions to read. */
export function docText(doc: RichText): string {
  const lines: string[] = [];
  const inline = (node: RichNode) => (node.type === "text" ? (node.text ?? "") : node.type === "hardBreak" ? "\n" : "");
  const block = (node: RichNode | RichText) => {
    if (node.type === "paragraph" || node.type === "heading") lines.push((node.content ?? []).map(inline).join(""));
    else for (const child of node.content ?? []) block(child);
  };
  block(doc);
  return lines.join("\n");
}
