// Where a name picked in the editor's Names drawer goes: the text field, rich text or
// rule the designer last wrote in. Each such field claims this when it gets the focus,
// and lets go when it leaves the page or when the designer goes on to write somewhere
// else, so a name never lands in a field other than the one being written.

export interface NameTarget {
  /** Puts the name where the caret was: {{name}} in text, a name chip in rich text, the bare name in a rule. */
  insert: (name: string) => void;
  /** What the field is called, for saying where the name went. */
  label: string;
  /** The field itself. */
  element: HTMLElement;
}

export const nameTarget = $state<{ current: NameTarget | null }>({ current: null });

/** Makes target where picked names go; the returned function lets go, if it's still the one. */
export function claimNames(target: NameTarget): () => void {
  nameTarget.current = target;
  return () => {
    if (nameTarget.current === target) nameTarget.current = null;
  };
}

/**
 * The claim ends when the focus goes to another field to write in. Buttons, and
 * everything in the Names drawer itself (where the name is picked), leave it be.
 */
export function movedOn(focused: EventTarget | null): void {
  const target = nameTarget.current;
  if (!target || !(focused instanceof HTMLElement) || target.element.contains(focused)) return;
  if (focused.closest("#names-drawer") || !focused.matches("input, textarea, select, [contenteditable='true'], [contenteditable='']")) return;
  nameTarget.current = null;
}

