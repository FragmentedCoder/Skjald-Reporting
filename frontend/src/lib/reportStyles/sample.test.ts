import { describe, expect, it } from "vitest";
import type { CustomField } from "#lib/customFields.js";
import type { LibraryEntry } from "#lib/library.js";
import { preview } from "#lib/templates/preview.js";
import { textKey } from "./look";
import { element, resolve } from "./resolve";
import { sampleReport } from "./sample";

const phone: LibraryEntry = {
  id: 1, kind: "variable", key: "support_phone", description: "", value: { value: "+45 70 20 30 40" },
  version: 1, updated_at: "", updated_by: null, locked: false, locked_by: null,
};
const agreement: CustomField = {
  id: 1, applies_to: "customer", key: "agreement", label: "Support agreement", type: "dropdown", help: "",
  options: ["Gold", "Silver"], position: 0, archived: false, version: "v1",
};

describe("the style editor's sample report", () => {
  const footer = element({ id: "e_footer", kind: "text", x: 18, y: 285, w: 150, h: 5, text: "Support: {{ vars.support_phone }} ({{ customer.custom.agreement }})" });
  const style = resolve([{ pages: { other: { elements: [footer] } } }]);
  const key = textKey("other", "e_footer");

  it("fills in what a page design reads from the shared library and custom fields", () => {
    const input = sampleReport(style, [phone], [agreement], "Europe/Copenhagen");
    expect(input.library?.names).toEqual({ "vars.support_phone": "string", "customer.custom.agreement": "string" });
    expect(preview(input).pageTexts[key]).toBe("Support: +45 70 20 30 40 (Gold)");
  });

  it("can't fill in a library entry it isn't given", () => {
    const filled = preview(sampleReport(style, [], [agreement])).pageTexts[key];
    expect(filled).not.toContain("+45 70 20 30 40");
    expect(filled).toContain("(Gold)");
  });
});
