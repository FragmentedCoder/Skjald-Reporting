// Suggesting names while text is typed: after an unclosed "{{", the names that match
// what follows it, for text fields and the rich text editor alike.

import type { NameEntry } from "./catalogue";

/** The name being typed at the caret: where its "{{" starts, and what's typed after it. */
export function typedName(before: string): { start: number; query: string } | null {
  const match = /\{\{\s*([A-Za-z_][\w.]*)?$/.exec(before);
  return match ? { start: match.index, query: match[1] ?? "" } : null;
}

/** Names that print a value: not whole tables or other structures. */
export function printable(entries: NameEntry[]): NameEntry[] {
  return entries.filter((e) => e.shape !== "rows" && e.shape !== "other");
}

/** The names matching what's typed: names starting with it first, then names and labels holding it. */
export function matching(entries: NameEntry[], query: string, limit = 50): NameEntry[] {
  const q = query.toLowerCase();
  if (!q) return entries.slice(0, limit);
  const rank = (e: NameEntry) => {
    const name = e.name.toLowerCase();
    if (name.startsWith(q)) return 0;
    if (name.split(".").some((part) => part.startsWith(q))) return 1;
    if (name.includes(q) || e.label.toLowerCase().includes(q)) return 2;
    return 3;
  };
  return entries
    .map((entry, index) => ({ entry, index, rank: rank(entry) }))
    .filter((r) => r.rank < 3)
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .slice(0, limit)
    .map((r) => r.entry);
}

/** Text with a typed name completed: "{{" and what follows it up to the caret become "{{name}}". */
export function complete(text: string, caret: number, name: string): { text: string; caret: number } {
  const typed = typedName(text.slice(0, caret));
  const start = typed ? typed.start : caret;
  const after = text.slice(caret);
  const closing = /^\s*\}\}/.test(after) ? "" : "}}";
  const inserted = `{{${name}${closing}`;
  const next = text.slice(0, start) + inserted + after;
  return { text: next, caret: start + inserted.length + (closing ? 0 : after.indexOf("}}") + 2) };
}
