import { describe, expect, it } from "vitest";
import { drawn, strokePath } from "./signature";

describe("a drawn signature", () => {
  it("is its strokes, or nothing when it isn't signed or isn't lines", () => {
    expect(drawn({ strokes: [[10, 20, 30, 40]] })).toEqual([[10, 20, 30, 40]]);
    for (const not of [null, undefined, "", "data:image/png;base64,AAAA", { strokes: [] }, { strokes: [[1]] }, { strokes: [[1, 2, 3]] }, { strokes: [[1, "2"]] }, { strokes: "x" }]) {
      expect(drawn(not)).toBeNull();
    }
  });

  it("draws as one path, kept on the sheet, a single point as a dot", () => {
    expect(strokePath([[10, 20, 30.26, 40], [5, 5]])).toBe("M10 20L30.3 40M5 5h0.1");
    expect(strokePath([[-5, 250, 700, 100]])).toBe("M0 200L600 100");
  });
});
