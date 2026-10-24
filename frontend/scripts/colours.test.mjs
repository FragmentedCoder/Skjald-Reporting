import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { ACCENT, PRIMARY } from "../src/lib/colours.ts";

// The server stores only colour names and accepts only its own list.
test("the colour names match backend/app/colours.py", () => {
  const python = readFileSync(new URL("../../backend/app/colours.py", import.meta.url), "utf8");
  const names = (type) =>
    [...(python.match(new RegExp(`${type} = Literal\\[([^\\]]*)\\]`))?.[1] ?? "").matchAll(/"(\w+)"/g)].map(
      (m) => m[1],
    );
  expect(names("PrimaryColour")).toEqual(PRIMARY.map((s) => s.key));
  expect(names("AccentColour")).toEqual(ACCENT.map((s) => s.key));
});
