import { describe, expect, it } from "vitest";
import { lookOf, pageTexts, plainLook, pointsToCqi, textKey } from "./look";
import { element, resolve } from "./resolve";

const ART_1 = "1".repeat(64);
const ART_2 = "2".repeat(64);
const margins = { top: 45, bottom: 30, left: 25, right: 25 };

describe("a page look", () => {
  it("is plain in the Skjald default", () => {
    const look = plainLook();
    expect(look.art).toEqual({ first: null, other: null });
    expect(look.margins).toEqual(resolve([]).margins);
    expect(look.madeWith).toBe(true);
  });

  it("uses the style's artwork", () => {
    const style = resolve([{ artwork: { first: ART_1, other: ART_2 } }]);
    const look = lookOf(style, { image: (sha) => `/art/${sha.slice(0, 1)}` });
    expect(look.art).toEqual({ first: "/art/1", other: "/art/2" });
  });

  it("puts a customer's background over the artwork, with its margins", () => {
    const style = resolve([{ artwork: { first: ART_1, other: ART_2 } }]);
    const one = lookOf(style, { image: (sha) => sha, customerArt: { pages: ["/bg/1"], margins } });
    expect(one.art).toEqual({ first: "/bg/1", other: "/bg/1" });
    expect(one.margins).toEqual(margins);
    const two = lookOf(style, { customerArt: { pages: ["/bg/1", "/bg/2"], margins } });
    expect(two.art).toEqual({ first: "/bg/1", other: "/bg/2" });
    const none = lookOf(style, { image: (sha) => sha, customerArt: { pages: [], margins } });
    expect(none.art.first).toBe(ART_1);
  });

  it("lists the words of text elements to fill in", () => {
    const tagline = element({ id: "e_tagline", kind: "text", x: 18, y: 285, w: 100, h: 5, text: "{{ company.name }}" });
    const style = resolve([{ pages: { other: { elements: [tagline] } } }]);
    expect(pageTexts(style)).toEqual({ [textKey("other", "e_tagline")]: "{{ company.name }}" });
  });

  it("sizes text as a share of the page", () => {
    expect(pointsToCqi(72)).toBeCloseTo(12.095, 3);
  });
});
