// A template's text and rules gathered by element, as the Strings view shows them and a
// .skjald file's strings.json and rules.json hold them: "<element id>/<path>", such as
// "q_summary/label" or "b_cover/facts/0/value". The server gathers them the same way
// (backend/app/templates/files.py); shared/templates/strings.json holds both to one answer.

import type { RichText, TemplateContent } from "./types";

const TEXT_KEYS = new Set(["title", "subtitle", "label", "help", "valid_message", "text", "caption", "empty_text", "intro", "placeholder", "pattern_message", "unit", "yes_label", "no_label"]);
const RICH_KEYS = new Set(["content", "intro"]);
const RULE_KEYS = new Set(["visible_when", "required_when", "valid_when", "default", "tone_rule", "repeat_for", "value"]);

type Kind = "text" | "rich" | "rule";
type Found = { kind: Kind; address: string; value: unknown; key: string };

const isDoc = (value: unknown): value is RichText => !!value && typeof value === "object" && (value as { type?: unknown }).type === "doc";

function kindOf(node: Record<string, unknown>, key: string, value: unknown, parentKey: string | null): Kind | null {
  const own = typeof node.id === "string";
  if (RICH_KEYS.has(key) && isDoc(value)) return "rich";
  if (typeof value === "string" && (TEXT_KEYS.has(key) || (key === "value" && parentKey === "facts"))) return "text";
  if (RULE_KEYS.has(key) && own && typeof value === "string") return "rule";
  return null;
}

function* walk(node: unknown, anchor: string, path: string[], parentKey: string | null): Generator<Found> {
  if (Array.isArray(node)) {
    for (const [i, item] of node.entries()) yield* walk(item, anchor, [...path, String(i)], parentKey);
    return;
  }
  if (!node || typeof node !== "object") return;
  const record = node as Record<string, unknown>;
  const own = typeof record.id === "string" ? record.id : null;
  const [here, rel] = own ? [own, []] : [anchor, path];
  for (const [key, value] of Object.entries(record)) {
    const address = [here, ...rel, key].join("/");
    const kind = kindOf(record, key, value, parentKey);
    if (kind === "text") {
      if (value) yield { kind, address, value, key };
    } else if (kind) {
      yield { kind, address, value, key };
    } else if (value && typeof value === "object") {
      yield* walk(value, here, [...rel, key], key);
    }
  }
}

function* parts(content: TemplateContent): Generator<Found> {
  yield* walk(content.form, "form", [], null);
  yield* walk(content.layout, "layout", [], null);
}

/** Every piece of text (plain and not empty, or a rich text document), by address. */
export function strings(content: TemplateContent): Record<string, string | RichText> {
  const found: Record<string, string | RichText> = {};
  for (const f of parts(content)) if (f.kind !== "rule") found[f.address] = f.value as string | RichText;
  return found;
}

/** Every expression, by address. */
export function rules(content: TemplateContent): Record<string, string> {
  const found: Record<string, string> = {};
  for (const f of parts(content)) if (f.kind === "rule") found[f.address] = f.value as string;
  return found;
}

function put(node: unknown, anchor: string, path: string[], wanted: Record<string, unknown>, kinds: Set<Kind>, parentKey: string | null, done: Set<string>) {
  if (Array.isArray(node)) {
    for (const [i, item] of node.entries()) put(item, anchor, [...path, String(i)], wanted, kinds, parentKey, done);
    return;
  }
  if (!node || typeof node !== "object") return;
  const record = node as Record<string, unknown>;
  const own = typeof record.id === "string" ? record.id : null;
  const [here, rel] = own ? [own, []] : [anchor, path];
  for (const [key, value] of Object.entries(record)) {
    const address = [here, ...rel, key].join("/");
    const kind = kindOf(record, key, value, parentKey);
    if (address in wanted && kind && kinds.has(kind)) {
      record[key] = wanted[address];
      done.add(address);
    } else if (value && typeof value === "object") {
      put(value, here, [...rel, key], wanted, kinds, key, done);
    }
  }
}

/** Puts strings and rules back by address, in place; returns the addresses that named nothing. */
export function apply(content: TemplateContent, texts: Record<string, unknown> = {}, expressions: Record<string, string> = {}): string[] {
  const missing: string[] = [];
  for (const [wanted, kinds] of [[texts, new Set<Kind>(["text", "rich"])], [expressions, new Set<Kind>(["rule"])]] as const) {
    const done = new Set<string>();
    put(content.form, "form", [], wanted, kinds, null, done);
    put(content.layout, "layout", [], wanted, kinds, null, done);
    missing.push(...Object.keys(wanted).filter((a) => !done.has(a)));
  }
  return missing;
}
