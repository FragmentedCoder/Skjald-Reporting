import { describe, expect, it } from "vitest";
import type { LibraryEntry } from "#lib/library.js";
import { catalogue } from "./catalogue";
import { nameGroups, searchNames, shown, valueOf } from "./nameGroups";
import { sampleContext } from "./preview";

const table: LibraryEntry = {
  id: 1, kind: "table", key: "cvss", description: "Severity for each CVSS rating", value: { key_label: "Rating", columns: ["Severity"], rows: { "9.0": ["Critical"] } },
  version: 1, locked: false, locked_by: null, updated_at: "2026-11-01T10:00:00Z", updated_by: "Freja Holm",
};

describe("nameGroups", () => {
  const groups = nameGroups(catalogue(null), sampleContext(), [table]);

  it("lists the report's context with descriptions, kinds and examples, and data tables last", () => {
    const company = groups.find((g) => g.title === "Company");
    expect(company?.rows[0]).toEqual({ name: "company.name", what: "The company name printed on reports", kind: "text", example: '"Nordlys IT ApS"' });
    expect(groups.find((g) => g.title === "Author")?.rows.map((r) => r.name)).toContain("author.company");
    expect(groups.at(-1)).toMatchObject({ title: "Data tables", rows: [{ name: 'lookup("cvss", key)', kind: "data table", example: "1 row: Rating → Severity" }] });
  });

  it("finds names by every word searched for, in the name, what it is or the group", () => {
    expect(searchNames(groups, "company").flatMap((g) => g.rows.map((r) => r.name))).toEqual(expect.arrayContaining(["company.name", "author.company", "reviewer.company"]));
    expect(searchNames(groups, "reviewer phone").flatMap((g) => g.rows.map((r) => r.name))).toEqual(["reviewer.phone"]);
    expect(searchNames(groups, "nothing like this")).toEqual([]);
    expect(searchNames(groups, "  ")).toBe(groups);
  });

  it("marks which examples are current values, given them: the library's always are", () => {
    const marked = nameGroups(catalogue(null, { "vars.desk": "string" }, { "vars.desk": "Service desk" }), sampleContext(), [table], new Set(["company.name"]));
    const rows = marked.flatMap((g) => g.rows);
    expect(rows.find((r) => r.name === "company.name")?.live).toBe(true);
    expect(rows.find((r) => r.name === "report.number")?.live).toBe(false);
    expect(rows.find((r) => r.name === "vars.desk")?.live).toBe(true);
    expect(rows.find((r) => r.name === 'lookup("cvss", key)')?.live).toBe(true);
    expect(groups.flatMap((g) => g.rows).some((r) => "live" in r)).toBe(false);
  });
});

describe("shown and valueOf", () => {
  it("shows a sample value the way the lists do", () => {
    expect(shown(valueOf({ customer: { name: "Fjordvik" } }, "customer.name"))).toBe('"Fjordvik"');
    expect(shown(valueOf({}, "customer.name"))).toBe("—");
    expect(shown(3)).toBe("3");
  });
});
