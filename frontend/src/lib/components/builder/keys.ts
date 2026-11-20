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
  if (target?.closest("input, textarea, select, [contenteditable='true'], [contenteditable=''], dialog, [role='dialog']")) return null;
  return key === "y" || event.shiftKey ? "redo" : "undo";
}
