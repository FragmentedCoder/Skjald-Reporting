import { describe, expect, it } from "vitest";
import { isArtwork, type StyleAsset } from "./api";

const asset = (content_type: string, width: number, height: number): StyleAsset => ({ sha256: "a".repeat(64), content_type, width, height });

describe("a style's pictures", () => {
  it("are artwork when they're an SVG shaped like an A4 page", () => {
    // A letterhead converted from a PDF, a PNG of a page as the server wraps it, and
    // an SVG of a page drawn large.
    expect(isArtwork(asset("image/svg+xml", 595, 842))).toBe(true);
    expect(isArtwork(asset("image/svg+xml", 210, 297))).toBe(true);
    expect(isArtwork(asset("image/svg+xml", 2480, 3508))).toBe(true);
  });

  it("are images to place otherwise", () => {
    expect(isArtwork(asset("image/svg+xml", 640, 150))).toBe(false);
    expect(isArtwork(asset("image/svg+xml", 600, 600))).toBe(false);
    expect(isArtwork(asset("image/png", 595, 842))).toBe(false);
    expect(isArtwork(asset("image/jpeg", 2480, 3508))).toBe(false);
  });
});
