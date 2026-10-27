import { describe, expect, it } from "vitest";
import cases from "../../../../shared/styles/cases.json";
import { contrastProblems, emptyContent, resolve, type StyleContent } from "./resolve";

function at(value: unknown, path: string): unknown {
  let found: unknown = value;
  for (const part of path.split(".")) {
    if (part === "length") return (found as unknown[]).length;
    found = Array.isArray(found) ? found[Number(part)] : (found as Record<string, unknown>)[part];
  }
  return found;
}

describe("the shared stacking cases", () => {
  for (const c of cases.cases) {
    it(c.name, () => {
      const resolved = resolve(c.layers as unknown as Partial<StyleContent>[]);
      for (const [path, expected] of Object.entries(c.expect)) expect(at(resolved, path), path).toEqual(expected);
    });
  }
});

describe("styles", () => {
  it("leave the layers they stack on as they were", () => {
    const layer = { ...emptyContent(), colours: { text: "#000000" } };
    const once = resolve([layer]);
    once.colours.heading = "#FF0000";
    once.pages.first.elements.pop();
    expect(resolve([]).colours.heading).toBe("#0F1B2D");
    expect(resolve([]).pages.first.elements).toHaveLength(4);
  });

  it("read well in the Skjald default, and warn when they don't", () => {
    expect(contrastProblems(resolve([]))).toEqual([]);
    const pale = resolve([{ colours: { muted: "#AAAAAA" }, tones: { warning: { fill: "#FBEFD9", ink: "#E0A04A" } } }]);
    expect(contrastProblems(pale).map((p) => p.what)).toEqual(["Muted text", "Warning callouts"]);
  });
});
