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
