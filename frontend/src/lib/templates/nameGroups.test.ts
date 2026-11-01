import { describe, expect, it } from "vitest";
import incident from "../../../../shared/templates/incident.json";
import type { LibraryEntry } from "#lib/library.js";
import { catalogue, rowNames } from "./catalogue";
import { check } from "./checks";
import { nameGroups, searchNames, shown, valueOf } from "./nameGroups";
import { sampleContext } from "./preview";
import { printable } from "./suggest";
import type { TemplateContent } from "./types";

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

describe("names read from rows", () => {
  const content = structuredClone(incident) as unknown as TemplateContent;
  const entries = catalogue(content);
  const attackers = entries.find((e) => e.name === "answers.attackers");

  it("offers how many rows, the first row's columns and a text column from every row", () => {
    expect(rowNames(attackers!).map((e) => [e.name, e.label])).toEqual([
      ["size(answers.attackers)", "Attacking addresses: how many rows"],
      ["answers.attackers[0].ip", "Attacking addresses: Address, first row"],
      ["answers.attackers[0].attempts", "Attacking addresses: Sign-in attempts, first row"],
      ["answers.attackers[0].status", "Attacking addresses: Status, first row"],
      ['answers.attackers.map(row, row.ip).join(", ")', "Attacking addresses: Address, every row"],
      ['answers.attackers.map(row, row.status).join(", ")', "Attacking addresses: Status, every row"],
    ]);
    // Text suggests them in place of the list, which can't be printed whole.
    const names = printable(entries).map((e) => e.name);
    expect(names).toContain("answers.attackers[0].ip");
    expect(names).not.toContain("answers.attackers");
  });

  it("gives names a text block can print", () => {
    const text = rowNames(attackers!).map((e) => `{{${e.name}}}`).join(" ");
    content.layout.push({ id: "b_rows1", kind: "heading", visible_when: null, text });
    expect(check(content)).toEqual([]);
  });

  it("shows examples from the list's own", () => {
    const values = { answers: { attackers: [{ ip: "198.51.100.23", attempts: 1204, status: "blocked" }, { ip: "203.0.113.77", attempts: 611, status: "" }] } };
    const rows = nameGroups(entries, values).find((g) => g.title === "Answers")?.rows ?? [];
    const example = (name: string) => rows.find((r) => r.name === name)?.example;
    expect(example("answers.attackers")).toBe("2 rows");
    expect(example("size(answers.attackers)")).toBe("2");
    expect(example("answers.attackers[0].attempts")).toBe("1204");
    expect(example('answers.attackers.map(row, row.ip).join(", ")')).toBe('"198.51.100.23, 203.0.113.77"');
    expect(example('answers.attackers.map(row, row.status).join(", ")')).toBe('"blocked"');
    expect(rows.find((r) => r.name === "answers.attackers[0].ip")).toMatchObject({ field: "repeating", kind: "text" });
  });
});
