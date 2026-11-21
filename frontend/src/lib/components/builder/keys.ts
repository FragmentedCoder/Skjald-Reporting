// Keys the builder answers to, besides the ones fields and buttons handle themselves.

/**
 * Whether a key press asks to remove what's selected: Delete, or Backspace (the Mac's
 * delete key), on its own, and not while typing in a field or with a dialog open.
 */
export function removesSelection(event: KeyboardEvent): boolean {
  if (event.key !== "Delete" && event.key !== "Backspace") return false;
  if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || event.defaultPrevented) return false;
  const target = event.target instanceof Element ? event.target : null;
  return !target?.closest("input, textarea, select, [contenteditable='true'], [contenteditable=''], dialog, [role='dialog']");
}

// Kinds of <input> nobody types in: they keep no typing of their own to undo.
const UNTYPED = new Set(["checkbox", "radio", "range", "color", "file", "button", "submit", "reset"]);

/**
 * Whether a key press asks to undo (Ctrl or ⌘ with Z) or redo (with Shift too, or Ctrl
 * with Y) a change to the template. Not while typing in a field, which undoes its own
 * typing, nor with a dialog open.
 */
export function undoes(event: KeyboardEvent): "undo" | "redo" | null {
  if (!(event.ctrlKey || event.metaKey) || event.altKey || event.defaultPrevented) return null;
  const key = event.key.toLowerCase();
  if (key !== "z" && key !== "y") return null;
  const target = event.target instanceof Element ? event.target : null;
  if (target?.closest("textarea, [contenteditable='true'], [contenteditable=''], dialog, [role='dialog']")) return null;
  // A box that's typed in undoes its own typing; one that's ticked or chosen from has
  // nothing of its own to undo, so the template's change is taken back.
  if (target instanceof HTMLInputElement && !UNTYPED.has(target.type)) return null;
  return key === "y" || event.shiftKey ? "redo" : "undo";
}
