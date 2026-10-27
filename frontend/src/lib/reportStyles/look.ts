// How a report's pages look in the preview: a stacked style, the art behind the pages and
// the margins that go with it, the logos, and the words of the page designs' text
// elements once their expressions are filled in.
//
// The art is the customer's report background when the template uses it and the
// customer has one (its first page behind the report's first page and its second, or
// its only one, behind the rest, with its own margins); otherwise the style's artwork.

import type { Margins, PageName, ResolvedStyle } from "./resolve";
import { PAGE_NAMES, resolve } from "./resolve";

export interface PageLook {
  style: ResolvedStyle;
  /** Pictures behind the pages, by URL: the report's first page's and the rest's. */
  art: { first: string | null; other: string | null };
  margins: Margins;
  /** Where to load one of the style's pictures from. */
  image: (sha: string) => string | null;
  logos: { company: string | null; customer: string | null };
  /** The small "Made with Skjald" line, unless an Administrator turned it off. */
  madeWith: boolean;
  /** Text elements' words, filled in, by textKey(). */
  texts: Record<string, string>;
}

export interface CustomerArt {
  pages: string[];
  margins: Margins;
}

export function textKey(page: PageName, id: string): string {
  return `page:${page}:${id}`;
}

/** Every text element's words, by textKey(), for the preview to fill in. */
export function pageTexts(style: ResolvedStyle): Record<string, string> {
  const texts: Record<string, string> = {};
  for (const page of PAGE_NAMES) {
    for (const e of style.pages[page].elements) if (e.kind === "text") texts[textKey(page, e.id)] = e.text;
  }
  return texts;
}

export function lookOf(
  style: ResolvedStyle,
  options: {
    image?: (sha: string) => string | null;
    customerArt?: CustomerArt | null;
    logos?: { company: string | null; customer: string | null };
    madeWith?: boolean;
    texts?: Record<string, string>;
  } = {},
): PageLook {
  const image = options.image ?? (() => null);
  const customer = options.customerArt?.pages.length ? options.customerArt : null;
  return {
    style,
    art: customer
      ? { first: customer.pages[0], other: customer.pages[1] ?? customer.pages[0] }
      : { first: style.artwork.first ? image(style.artwork.first) : null, other: style.artwork.other ? image(style.artwork.other) : null },
    margins: customer ? customer.margins : style.margins,
    image,
    logos: options.logos ?? { company: null, customer: null },
    madeWith: options.madeWith ?? true,
    texts: options.texts ?? {},
  };
}

/** The Skjald default, as the preview shows it before a style is chosen. */
export function plainLook(): PageLook {
  return lookOf(resolve([]));
}

/** Points to the share of an A4 page's width (210 mm) they are, in cqi. */
export function pointsToCqi(points: number, pageWidthMm = 210): number {
  return ((points * 25.4) / 72 / pageWidthMm) * 100;
}

export const FONT_STACKS: Record<string, string> = {
  marcellus: "var(--font-display)",
  "plex-sans": "var(--font-sans)",
  "plex-mono": "var(--font-mono)",
};
