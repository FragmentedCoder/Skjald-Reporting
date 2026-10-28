import { describe, expect, it } from "vitest";
import { entryName, libraryNames, libraryValues, type LibraryEntry } from "./library";

const entry = (kind: LibraryEntry["kind"], key: string, value: LibraryEntry["value"]): LibraryEntry => ({
  id: 1, kind, key, description: "", value, version: 1, updated_at: "", updated_by: null, locked: false, locked_by: null,
});

describe("what templates read from the library", () => {
  const entries = [
    entry("variable", "support_phone", { value: "+45 70 20 30 40" }),
    entry("snippet", "handover", { text: "Call {{vars.support_phone}}, or {{vars.missing}}." }),
    entry("table", "severity", { key_label: "Level", columns: ["Label"], rows: { high: ["Høj"] } }),
  ];

  it("names variables and snippets as the server does", () => {
    expect(libraryNames(entries)).toEqual({ "vars.support_phone": "string", "text.handover": "string" });
    expect(entries.map(entryName)).toEqual(["vars.support_phone", "text.handover", 'lookup("severity", key)']);
  });

  it("fills snippets' variables in, and gives tables to lookup()", () => {
    const { values, tables } = libraryValues(entries);
    expect(values).toEqual({ vars: { support_phone: "+45 70 20 30 40" }, text: { handover: "Call +45 70 20 30 40, or ." } });
    expect(tables).toEqual({ severity: { columns: ["Label"], rows: { high: ["Høj"] } } });
  });
});
