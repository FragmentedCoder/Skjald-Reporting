// Report styles as the browser stacks them: the Skjald default (shared/styles/default.json),
// then a company style, then a customer style, each holding only what it changes from
// the layer below. The server stacks them the same way (backend/app/styles/content.py);
// shared/styles/cases.json holds both to the same answers. Colours, fonts, sizes and
// margins stack key by key and a tone as a pair; a page design and the artwork replace
// the layer below's as a whole.

import { contrast } from "#lib/colours.js";
import { defaultStyle } from "#lib/shared.js";

export type Font = "marcellus" | "plex-sans" | "plex-mono";
export const COLOUR_KEYS = ["text", "muted", "heading", "accent", "link", "line", "table_head", "table_head_text", "classification"] as const;
export type ColourKey = (typeof COLOUR_KEYS)[number];
/** Colours a page design's element can name instead of giving one. */
export const NAMED_COLOURS = ["text", "muted", "heading", "accent", "link", "line", "classification"] as const;
export const TONE_NAMES = ["info", "note", "warning", "critical", "success"] as const;
export type ToneName = (typeof TONE_NAMES)[number];
export const PAGE_NAMES = ["cover", "first", "other"] as const;
export type PageName = (typeof PAGE_NAMES)[number];
export const ELEMENT_KINDS = ["text", "logo", "image", "line", "box", "page_number", "classification", "report_number"] as const;
export type ElementKind = (typeof ELEMENT_KINDS)[number];

export interface Tone {
  fill: string;
  ink: string;
}

export interface Margins {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export interface Element {
  id: string;
  kind: ElementKind;
  x: number;
  y: number;
  w: number;
  h: number;
  text: string;
  font: "heading" | "body" | "mono";
  size: number;
  colour: string;
  weight: "regular" | "bold";
  align: "left" | "center" | "right";
  logo: "company" | "customer";
  asset: string | null;
  fill: string | null;
  stroke: string | null;
  stroke_width: number;
  radius: number;
}

export interface PageDesign {
  elements: Element[];
}

export interface Artwork {
  first: string | null;
  other: string | null;
}

export interface StyleContent {
  colours: Partial<Record<ColourKey, string | null>>;
  tones: Partial<Record<ToneName, Tone | null>>;
  fonts: { heading?: Font | null; body?: Font | null };
  sizes: { body?: number | null; title?: number | null };
  margins: Partial<Record<keyof Margins, number | null>>;
  pages: Partial<Record<PageName, PageDesign | null>>;
  artwork: Artwork | null;
}

export interface ResolvedStyle {
  colours: Record<ColourKey, string>;
  tones: Record<ToneName, Tone>;
  fonts: { heading: Font; body: Font };
  sizes: { body: number; title: number };
  margins: Margins;
  pages: Record<PageName, PageDesign>;
  artwork: Artwork;
}

const ELEMENT_DEFAULTS = {
  text: "",
  font: "body",
  size: 9,
  colour: "text",
  weight: "regular",
  align: "left",
  logo: "company",
  asset: null,
  fill: null,
  stroke: "line",
  stroke_width: 0.3,
  radius: 0,
} as const;

/** An element with every setting it leaves out at its default. */
export function element(given: Partial<Element> & Pick<Element, "id" | "kind" | "x" | "y" | "w" | "h">): Element {
  return { ...ELEMENT_DEFAULTS, ...given } as Element;
}

function design(given: { elements: Partial<Element>[] }): PageDesign {
  return { elements: given.elements.map((e) => element(e as Element)) };
}

/** A style with nothing changed: it looks like the layer below. */
export function emptyContent(): StyleContent {
  return { colours: {}, tones: {}, fonts: {}, sizes: {}, margins: {}, pages: {}, artwork: null };
}

function set<T extends object>(values: T | undefined): Partial<T> {
  return Object.fromEntries(Object.entries(values ?? {}).filter(([, v]) => v !== null && v !== undefined)) as Partial<T>;
}

/** The Skjald default with each layer stacked on it, bottom first. */
export function resolve(layers: Partial<StyleContent>[]): ResolvedStyle {
  const base = defaultStyle as unknown as ResolvedStyle;
  const out: ResolvedStyle = {
    colours: { ...base.colours },
    tones: { ...base.tones },
    fonts: { ...base.fonts },
    sizes: { ...base.sizes },
    margins: { ...base.margins },
    pages: { cover: design(base.pages.cover), first: design(base.pages.first), other: design(base.pages.other) },
    artwork: { ...base.artwork },
  };
  for (const layer of layers) {
    Object.assign(out.colours, set(layer.colours));
    Object.assign(out.tones, set(layer.tones));
    Object.assign(out.fonts, set(layer.fonts));
    Object.assign(out.sizes, set(layer.sizes));
    Object.assign(out.margins, set(layer.margins));
    for (const page of PAGE_NAMES) {
      const given = layer.pages?.[page];
      if (given) out.pages[page] = design(given);
    }
    if (layer.artwork) out.artwork = { first: layer.artwork.first ?? null, other: layer.artwork.other ?? null };
  }
  return out;
}

/** A colour an element names, as the style has it, or the colour it gives. */
export function colourOf(style: ResolvedStyle, ref: string): string {
  return ref.startsWith("#") ? ref : (style.colours[ref as ColourKey] ?? style.colours.text);
}

export const COLOUR_LABELS: Record<ColourKey, string> = {
  text: "Text",
  muted: "Muted text",
  heading: "Headings",
  accent: "Accent",
  link: "Links",
  line: "Lines",
  table_head: "Table header",
  table_head_text: "Table header text",
  classification: "Classification label",
};

export const TONE_LABELS: Record<ToneName, string> = { info: "Info", note: "Note", warning: "Warning", critical: "Critical", success: "Success" };

const PAPER = "#FFFFFF";
export const NEEDED = 4.5;

/** Text colours that read less well than WCAG AA's 4.5:1 against what they're on. */
export function contrastProblems(style: ResolvedStyle): { what: string; ratio: number }[] {
  const pairs: [string, string, string][] = [
    ["Text", style.colours.text, PAPER],
    ["Muted text", style.colours.muted, PAPER],
    ["Headings", style.colours.heading, PAPER],
    ["Links", style.colours.link, PAPER],
    ["Classification label", style.colours.classification, PAPER],
    ["Table header text", style.colours.table_head_text, style.colours.table_head],
    ...TONE_NAMES.map((t): [string, string, string] => [`${TONE_LABELS[t]} callouts`, style.tones[t].ink, style.tones[t].fill]),
  ];
  return pairs.map(([what, ink, fill]) => ({ what, ratio: contrast(ink, fill) })).filter((p) => p.ratio < NEEDED);
}
