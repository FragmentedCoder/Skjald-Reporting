// Where a name picked in the editor's Names drawer goes: the text field or rich text
// the designer last typed in, while it's still on the page. Each such field claims
// this when it gets the focus and lets go when it leaves the page.

export interface NameTarget {
  /** Puts {{name}} (or rich text's name chip) where the caret was. */
  insert: (name: string) => void;
  /** What the field is called, for saying where the name went. */
  label: string;
}

export const nameTarget = $state<{ current: NameTarget | null }>({ current: null });

/** Makes target where picked names go; the returned function lets go, if it's still the one. */
export function claimNames(target: NameTarget): () => void {
  nameTarget.current = target;
  return () => {
    if (nameTarget.current === target) nameTarget.current = null;
  };
}
