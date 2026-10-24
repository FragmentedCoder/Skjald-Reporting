// The colours people and Administrators can pick: a primary (links, focus rings,
// switches, primary buttons) and an accent (the marker on the current page in
// menus, highlighted commands). Each has a light-mode and a dark-mode value, and
// colours.test.ts checks every one for contrast (WCAG AA) on Skjald's surfaces.
// The names must match backend/app/colours.py; a test checks that too.

export interface Swatch {
  key: string;
  name: string;
  light: string;
  dark: string;
}

export const PRIMARY: Swatch[] = [
  { key: "fjord", name: "Fjord", light: "#2B5D8A", dark: "#5B9BD5" },
  { key: "pine", name: "Pine", light: "#2F6B47", dark: "#5FBF84" },
  { key: "teal", name: "Teal", light: "#1D6B73", dark: "#4FBFC9" },
  { key: "heather", name: "Heather", light: "#6A4C9C", dark: "#B49DE0" },
  { key: "rose", name: "Rose", light: "#A23A64", dark: "#EE93B7" },
  { key: "slate", name: "Slate", light: "#4A5568", dark: "#AAB4C3" },
];

export const ACCENT: Swatch[] = [
  { key: "rav", name: "Amber", light: "#C8862A", dark: "#E0A04A" },
  { key: "copper", name: "Copper", light: "#B5652B", dark: "#E39A62" },
  { key: "moss", name: "Moss", light: "#6B8E23", dark: "#A5C85A" },
  { key: "sky", name: "Sky", light: "#2E86C1", dark: "#6DB6E8" },
  { key: "rose", name: "Rose", light: "#C2416B", dark: "#EC8AAA" },
  { key: "violet", name: "Violet", light: "#7E57C2", dark: "#B39DDB" },
];

export const DEFAULT_PRIMARY = "fjord";
export const DEFAULT_ACCENT = "rav";

// Text on a primary button: white on the light-mode colour, near-black on the dark.
const ON_PRIMARY = { light: "#FFFFFF", dark: "#0B1420" };

export interface ColourChoice {
  primary: string | null;
  accent: string | null;
}

/** What applies: the site's colours when enforced, else the person's own, else the site's. */
export function effectiveColours(
  site: { primary_colour: string; accent_colour: string; enforce_colours: boolean },
  own: ColourChoice | null | undefined,
): { primary: string; accent: string } {
  if (site.enforce_colours || !own) {
    return { primary: site.primary_colour, accent: site.accent_colour };
  }
  return {
    primary: own.primary ?? site.primary_colour,
    accent: own.accent ?? site.accent_colour,
  };
}

/** The page's current mode, after the person's choice or the device's setting. */
export function currentMode(): "light" | "dark" {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Set the colours on the page. Skjald's own (Fjord and Amber) come from
 * tokens.css, so they clear any override: the primary button stays ink and snow
 * as docs/brand asks. Set through the CSSOM, which the page's CSP allows.
 */
export function applyColours(colours: { primary: string; accent: string }): void {
  const root = document.documentElement.style;
  const mode = currentMode();
  const primary = PRIMARY.find((s) => s.key === colours.primary);
  const accent = ACCENT.find((s) => s.key === colours.accent);
  for (const name of ["--link", "--button-bg", "--button-text", "--accent"]) {
    root.removeProperty(name);
  }
  if (primary && primary.key !== DEFAULT_PRIMARY) {
    root.setProperty("--link", primary[mode]);
    root.setProperty("--button-bg", primary[mode]);
    root.setProperty("--button-text", ON_PRIMARY[mode]);
  }
  if (accent && accent.key !== DEFAULT_ACCENT) root.setProperty("--accent", accent[mode]);
}
