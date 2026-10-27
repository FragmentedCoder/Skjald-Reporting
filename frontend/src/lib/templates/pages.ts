// How printed blocks fall onto pages: the page rules the preview and the renderer
// share (docs/architecture.md). The cover gets a page of its own; a section set to
// start on a new page begins one, a page break forces one, and a landscape section
// gets landscape pages of its own; no rule ever leaves an empty page. Sections are
// numbered (1, 1.1, 2) and tables and figures counted in reading order, only what's
// printed. Long content flowing onto more pages is the renderer's job; the preview
// flags a page that runs over. shared/pages/cases.json holds the rules for both.

import type { Shown } from "./preview";

export interface Placed {
  block: Shown;
  depth: number;
  /** A section's number, such as 2.1, when it's numbered. */
  number?: string;
  /** Table 1, Figure 2. */
  caption?: string;
}

export interface Page {
  orientation: "portrait" | "landscape";
  cover: boolean;
  items: Placed[];
  /** Why the page starts, for the builder to say. */
  reason: string;
}

export interface Contents {
  number: string | null;
  title: string;
  depth: number;
  page: number;
}

export interface Paged {
  pages: Page[];
  contents: Contents[];
}

export function paginate(blocks: Shown[]): Paged {
  const pages: Page[] = [];
  let current: Page | null = null;
  let breakNext: string | null = null;
  let tables = 0;
  let figures = 0;
  const contents: Contents[] = [];

  const start = (reason: string, orientation: Page["orientation"] = "portrait", cover = false) => {
    current = { orientation, cover, items: [], reason };
    pages.push(current);
    return current;
  };
  // The page to put the next thing on: a new one if a rule asks and this one has
  // something, or if it faces the wrong way.
  const page = (orientation: Page["orientation"], reason?: string): Page => {
    const here = current as Page | null;
    if (!here || here.cover) return start(reason ?? breakNext ?? "First page", orientation);
    const wanted = reason ?? breakNext;
    if (here.items.length && (wanted || here.orientation !== orientation)) {
      return start(wanted ?? (orientation === "landscape" ? "Landscape section" : "Back to portrait"), orientation);
    }
    if (!here.items.length) here.orientation = orientation;
    return here;
  };

  const place = (block: Shown, depth: number, prefix: string, counter: { n: number }, orientation: Page["orientation"]) => {
    if (block.kind === "page_break") {
      breakNext = "Page break";
      return;
    }
    if (block.kind === "cover") {
      start("Cover page", "portrait", true).items.push({ block, depth });
      breakNext = null;
      return;
    }
    if (block.kind === "section") {
      const facing = block.landscape ? "landscape" : orientation;
      const number = block.numbered ? `${prefix}${++counter.n}` : undefined;
      const target = page(facing, block.newPage ? `Section “${block.title}” starts a new page` : undefined);
      breakNext = null;
      target.items.push({ block, depth, number });
      contents.push({ number: number ?? null, title: block.title, depth, page: pages.length });
      const inner = { n: 0 };
      for (const child of block.blocks) place(child, depth + 1, number ? `${number}.` : prefix, inner, facing);
      if (block.landscape && orientation === "portrait") breakNext = breakNext ?? "Back to portrait";
      return;
    }
    const target = page(orientation);
    breakNext = null;
    const placed: Placed = { block, depth };
    if (block.kind === "table") placed.caption = `Table ${++tables}`;
    if (block.kind === "image" || block.kind === "gallery") placed.caption = `Figure ${++figures}`;
    target.items.push(placed);
  };

  const top = { n: 0 };
  for (const block of blocks) place(block, 0, "", top, "portrait");
  return { pages, contents };
}
