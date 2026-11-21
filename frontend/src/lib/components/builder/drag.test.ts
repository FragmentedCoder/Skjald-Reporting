import { describe, expect, it } from "vitest";
import { whileDragging } from "./drag.svelte";

const items = (...ids: string[]) => ids.map((id) => ({ id }));

describe("whileDragging", () => {
  it("shows the drag library's order while a list differs from its own", () => {
    const shadowed = items("a", "id:dnd-shadow-placeholder-0000", "b");
    expect(whileDragging(shadowed, items("a", "b"))).toBe(shadowed);
    const without = items("b");
    expect(whileDragging(without, items("a", "b"))).toBe(without);
  });

  it("goes on showing the drag while its placeholder is in the list, even with the block's own ID", () => {
    const home = [{ id: "a" }, { id: "b", isDndShadowItem: true }];
    expect(whileDragging(home, items("a", "b"))).toBe(home);
    const fromPalette = [{ id: "a" }, { id: "b", palette: true }];
    expect(whileDragging(fromPalette, items("a", "b"))).toBe(fromPalette);
  });

  it("lets go once the drag has left the list as it was", () => {
    expect(whileDragging(items("a", "b"), items("a", "b"))).toBeNull();
    expect(whileDragging([], [])).toBeNull();
  });
});
