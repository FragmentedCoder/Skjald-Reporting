import { describe, expect, it } from "vitest";
import type { NameEntry } from "./catalogue";
import { complete, matching, printable, typedName } from "./suggest";

const entry = (name: string, label: string, shape: NameEntry["shape"] = "text"): NameEntry => ({ name, label, group: "Test", type: "string", shape });

const ENTRIES = [
  entry("report.title", "The report's title"),
  entry("report.number", "The report's number"),
  entry("customer.name", "The customer's name"),
  entry("company.name", "The company name printed on reports"),
  entry("answers.hosts", "Affected hosts", "rows"),
];

describe("typedName", () => {
  it("finds an unclosed {{ and what's typed after it", () => {
    expect(typedName("Report for {{cust")).toEqual({ start: 11, query: "cust" });
    expect(typedName("{{")).toEqual({ start: 0, query: "" });
    expect(typedName("{{ customer.na")).toEqual({ start: 0, query: "customer.na" });
  });

  it("finds nothing once the name is closed or isn't a name", () => {
    expect(typedName("{{customer.name}}")).toBeNull();
    expect(typedName("{{customer.name}} and")).toBeNull();
    expect(typedName("{{a + b")).toBeNull();
    expect(typedName("plain text")).toBeNull();
  });
});

describe("matching", () => {
  it("puts names starting with what's typed first, then parts and labels", () => {
    expect(matching(printable(ENTRIES), "c").map((e) => e.name)).toEqual(["customer.name", "company.name"]);
    expect(matching(ENTRIES, "name").map((e) => e.name)).toEqual(["customer.name", "company.name"]);
    expect(matching(ENTRIES, "title").map((e) => e.name)).toEqual(["report.title"]);
    expect(matching(ENTRIES, "printed").map((e) => e.name)).toEqual(["company.name"]);
  });

  it("offers everything for nothing typed, and nothing for no match", () => {
    expect(matching(ENTRIES, "")).toHaveLength(ENTRIES.length);
    expect(matching(ENTRIES, "zzz")).toEqual([]);
  });

  it("leaves out names that don't print a value", () => {
    expect(printable(ENTRIES).map((e) => e.name)).not.toContain("answers.hosts");
  });
});

describe("complete", () => {
  it("completes what's typed, closing the braces", () => {
    expect(complete("Report for {{cust", 17, "customer.name")).toEqual({ text: "Report for {{customer.name}}", caret: 28 });
  });

  it("keeps the text after the caret, and braces already there", () => {
    expect(complete("{{cu}} and more", 4, "customer.name")).toEqual({ text: "{{customer.name}} and more", caret: 17 });
    expect(complete("A {{ and B", 4, "report.title")).toEqual({ text: "A {{report.title}} and B", caret: 18 });
  });

  it("inserts a whole name where nothing is typed", () => {
    expect(complete("Title: ", 7, "report.title")).toEqual({ text: "Title: {{report.title}}", caret: 23 });
  });
});
