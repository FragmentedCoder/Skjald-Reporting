// The page rules, against the cases the renderer will run too (shared/pages/cases.json).
import { describe, expect, it } from "vitest";
import cases from "../../../../shared/pages/cases.json";
import { paginate, type Placed } from "./pages";
import type { Shown } from "./preview";

interface Case {
  name: string;
  blocks: unknown[];
  pages: { orientation: string; cover: boolean; ids: string[] }[];
  numbers?: Record<string, string>;
  captions?: Record<string, string>;
  contents?: { number: string | null; title: string; depth: number; page: number }[];
}

describe("page rules", () => {
  it.each(cases.cases as Case[])("$name", (c) => {
    const { pages, contents } = paginate(c.blocks as Shown[]);
    expect(pages.map((p) => ({ orientation: p.orientation, cover: p.cover, ids: p.items.map((i) => i.block.id) }))).toEqual(c.pages);
    const placed: Placed[] = pages.flatMap((p) => p.items);
    expect(Object.fromEntries(placed.filter((i) => i.number).map((i) => [i.block.id, i.number]))).toEqual(c.numbers ?? {});
    expect(Object.fromEntries(placed.filter((i) => i.caption).map((i) => [i.block.id, i.caption]))).toEqual(c.captions ?? {});
    if (c.contents) expect(contents).toEqual(c.contents);
  });
});
