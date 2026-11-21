import { describe, expect, it } from "vitest";
import { interpolations, readTyped } from "./text";

describe("interpolations", () => {
  it("finds each {{ }} and what's in it, a map's braces included", () => {
    expect(interpolations('Hi {{ customer.name }}, {{ {"a": {"b": 1}} }}')).toEqual([
      { start: 3, end: 22, expr: "customer.name", closed: true },
      { start: 24, end: 45, expr: '{"a": {"b": 1}}', closed: true },
    ]);
    expect(interpolations("{{customer.na")).toEqual([{ start: 0, end: 13, expr: "customer.na", closed: false }]);
  });
});

describe("readTyped", () => {
  it("reads an expression, alone or in {{ }}", () => {
    expect(readTyped(' report.number + " for " + customer.name ')).toEqual({ expr: 'report.number + " for " + customer.name' });
    expect(readTyped("{{customer.name}}")).toEqual({ expr: "customer.name" });
    expect(readTyped("  {{ customer.name }} ")).toEqual({ expr: "customer.name" });
  });

  it("reads text with names in {{ }} as a text block's", () => {
    const read = readTyped("Report {{report.number}} for {{customer.name}}");
    expect("parts" in read && read.parts.map((p) => p.expr)).toEqual(["report.number", "customer.name"]);
    expect("parts" in readTyped("For {{customer.name}}")).toBe(true);
  });

  it("notices a name left open", () => {
    expect(readTyped("For {{customer.name")).toEqual({ unclosed: true });
  });
});
