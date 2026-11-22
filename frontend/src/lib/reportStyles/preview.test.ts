import { describe, expect, it } from "vitest";
import type { Style } from "./api";
import { imageOf, readsStyles } from "./preview.svelte";
import { emptyContent } from "./resolve";

const OWN = "1".repeat(64);
const BASE = "2".repeat(64);
const style: Style = {
  id: 7, name: "Fjordvik look", customer_id: 3, customer_name: "Fjordvik Logistik A/S", based_on: 4, is_default: false,
  version: 2, updated_at: "", updated_by: null, content: emptyContent(), below: [], problems: [],
  assets: [{ sha256: OWN, content_type: "image/png", width: 300, height: 100 }],
};

describe("where a style's pictures load from", () => {
  it("is the style itself, or the company style it stacks on", () => {
    const image = imageOf(style);
    expect(image(OWN)).toBe("/api/styles/7/assets/" + OWN);
    expect(image(BASE)).toBe("/api/styles/4/assets/" + BASE);
    expect(imageOf(null)(OWN)).toBeNull();
  });

  it("is the base chosen in the editor, before it's saved", () => {
    expect(imageOf(style, 9)(BASE)).toBe("/api/styles/9/assets/" + BASE);
    expect(imageOf(style, 9)(OWN)).toBe("/api/styles/7/assets/" + OWN);
    // The Skjald default has no pictures.
    expect(imageOf(style, null)(BASE)).toBeNull();
  });
});

describe("who may read styles", () => {
  it("is those who edit styles, build templates or manage customers", () => {
    expect(readsStyles(["edit_styles"])).toBe(true);
    expect(readsStyles(["build_templates", "edit_library"])).toBe(true);
    expect(readsStyles(["manage_customers", "manage_projects"])).toBe(true);
  });

  it("isn't a technician or a reviewer, whose report preview keeps the Skjald default", () => {
    expect(readsStyles(["create_reports", "fill_in_reports", "edit_library", "check_signed_reports"])).toBe(false);
    expect(readsStyles(["review_and_countersign", "check_signed_reports"])).toBe(false);
    expect(readsStyles([])).toBe(false);
  });
});
