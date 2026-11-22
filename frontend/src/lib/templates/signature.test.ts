import { describe, expect, it } from "vitest";
import { NAME_MAX, sign, signed } from "./signature";

describe("a signature question's answer", () => {
  const at = "2026-11-22T13:04:05Z";

  it("is signed when a name is confirmed, and says who and when", () => {
    expect(signed({ name: "Anna Berg", confirmed: true, at })).toEqual({ name: "Anna Berg", at: new Date(at) });
    expect(signed({ name: "  Anna Berg ", confirmed: true, at: "2026-11-22T14:04:05.250+01:00" })).toEqual({ name: "Anna Berg", at: new Date("2026-11-22T13:04:05.250Z") });
  });

  it("isn't signed without a name, a confirmation and the moment of it", () => {
    for (const not of [
      null, undefined, "", "Anna Berg", 7, true, [], [{ name: "Anna Berg", confirmed: true, at }],
      { name: "Anna Berg", at }, { name: "Anna Berg", confirmed: false, at }, { name: "Anna Berg", confirmed: "true", at },
      { name: "", confirmed: true, at }, { name: "   ", confirmed: true, at }, { name: 7, confirmed: true, at },
      { name: "x".repeat(NAME_MAX + 1), confirmed: true, at },
      { name: "Anna Berg", confirmed: true }, { name: "Anna Berg", confirmed: true, at: null }, { name: "Anna Berg", confirmed: true, at: 1795352645000 },
      { name: "Anna Berg", confirmed: true, at: "yesterday" }, { name: "Anna Berg", confirmed: true, at: "2026-11-22" },
      { name: "Anna Berg", confirmed: true, at: "2026-11-22T13:04:05" }, { name: "Anna Berg", confirmed: true, at: "2026-13-45T13:04:05Z" },
    ]) {
      expect(signed(not)).toBeNull();
    }
  });

  it("reads an answer drawn on the pad it replaced as not signed", () => {
    expect(signed({ strokes: [[10, 20, 30, 40], [50, 60]] })).toBeNull();
    expect(signed({ strokes: [[10, 20, 30, 40]], name: "Anna Berg" })).toBeNull();
  });

  it("is made of the name as typed, without the space around it, and the moment to the second", () => {
    const now = new Date("2026-11-22T13:04:05.678Z");
    expect(sign(" Anna Berg  ", now)).toEqual({ name: "Anna Berg", confirmed: true, at });
    expect(signed(sign("Anna Berg", now))).toEqual({ name: "Anna Berg", at: new Date(at) });
    expect(signed(sign("Søren Ærø-Ølgaard"))?.name).toBe("Søren Ærø-Ølgaard");
  });

  it("isn't made of a blank name, or one longer than the form takes", () => {
    expect(sign("")).toBeNull();
    expect(sign("   ")).toBeNull();
    expect(sign("x".repeat(NAME_MAX))).not.toBeNull();
    expect(sign("x".repeat(NAME_MAX + 1))).toBeNull();
  });
});
