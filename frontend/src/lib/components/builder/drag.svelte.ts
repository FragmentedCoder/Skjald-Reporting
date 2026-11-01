// What the builder's drag-and-drop lists share: how what's dragged looks, and the
// options every list gives svelte-dnd-action.

import { tick } from "svelte";
import { SHADOW_ITEM_MARKER_PROPERTY_NAME, type Item, type TransformDraggedElementFunction } from "svelte-dnd-action";

/**
 * How whatever is dragged looks: a small card under the pointer, naming it, the same
 * in every list. The drag library otherwise carries a copy of the element at its full
 * size, a section with all its blocks or a block from a page, which loses its look
 * once it's out of its list.
 */
export function dragLook<T extends Item>(describe: (data: T) => string): TransformDraggedElementFunction {
  return (element?: HTMLElement, data?: Item) => {
    if (!element || !data || element.dataset.dragLook) return;
    element.dataset.dragLook = "yes";
    const before = element.getBoundingClientRect();
    const icon = element.querySelector(".icon")?.cloneNode(true);
    const label = document.createElement("span");
    label.textContent = describe(data as T);
    Object.assign(label.style, { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" });
    element.replaceChildren(...(icon ? [icon] : []), label);
    Object.assign(element.style, {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      width: "max-content",
      maxWidth: "320px",
      height: "auto",
      padding: "6px 12px",
      border: "1px solid var(--link)",
      borderRadius: "var(--radius-md)",
      background: "var(--surface)",
      boxShadow: "0 10px 24px rgb(15 27 45 / 0.22)",
      color: "var(--text)",
      font: "600 13px/1.4 var(--font-sans)",
      opacity: "1",
      outline: "none",
    });
    // Smaller now: kept centred where it was, under the pointer, by its margins (the
    // library places the copy by its top and left, a moment later, for its first size).
    const after = element.getBoundingClientRect();
    element.style.marginLeft = `${(before.width - after.width) / 2}px`;
    element.style.marginTop = `${(before.height - after.height) / 2}px`;
  };
}

/**
 * What a list shows while something is dragged: the drag library's order, or (null) its
 * own blocks again once the drag has left it as it was. Lists only passed over hear
 * nothing when the drag ends, so they must let go as soon as it leaves them, or they'd
 * go on showing that moment's copy and miss every later change. A list holding the
 * drag's placeholder isn't as it was, even where the placeholder carries the dragged
 * block's own ID (over its starting place).
 */
export function whileDragging<T extends { id: string }>(items: T[], own: { id: string }[]): T[] | null {
  const unchanged = items.length === own.length
    && items.every((item, i) => item.id === own[i].id && !(SHADOW_ITEM_MARKER_PROPERTY_NAME in item) && !("palette" in item));
  return unchanged ? null : items;
}

/**
 * Options every list shares: the dragged card is centred on the pointer and keeps its
 * size, so where its centre is, the pointer is, and that says where it lands.
 */
export const DRAG_OPTIONS = { centreDraggedOnCursor: true, morphDisabled: true } as const;

/**
 * The drag library hooks up each card when a list's options change. A dropped card is
 * drawn again just after that, so it would be left unhooked and couldn't be dragged a
 * second time: once it's drawn, the options change once more (with `hooked`).
 */
export class Hooks {
  hooked = $state(0);

  /** Call on every drop. */
  again = () => void tick().then(() => this.hooked++);
}
