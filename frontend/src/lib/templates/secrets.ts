// How a secret field prints: the builder's copy of backend/app/templates/secrets.py.
// At most a quarter of its characters and three at each end, with a fixed run of dots
// that hides its length; shorter than eight characters, dots only. Characters are code
// points, as in Python.

export const DOTS = "••••••";

export function printed(secret: string, how: "partial" | "omit" = "partial"): string {
  if (how === "omit" || !secret) return "";
  const characters = Array.from(secret);
  const shown = Math.min(3, Math.floor(Math.floor(characters.length / 4) / 2));
  return characters.slice(0, shown).join("") + DOTS + (shown ? characters.slice(-shown).join("") : "");
}
