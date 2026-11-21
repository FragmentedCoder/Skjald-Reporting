import { describe, expect, it } from "vitest";
import { FIELD_TYPES, questionChoice, TYPE_CODES, typeCode } from "./fields";

describe("field type shorthands", () => {
  it("gives every type two capital letters of its own", () => {
    expect(Object.keys(TYPE_CODES).sort()).toEqual(Object.keys(FIELD_TYPES).sort());
    const codes = Object.values(TYPE_CODES);
    expect(codes.every((c) => /^[A-Z]{2}$/.test(c))).toBe(true);
    expect(new Set(codes).size).toBe(codes.length);
    expect(typeCode("yes_no")).toBe("YN");
    expect(typeCode("table")).toBe("TB");
  });

  it("names a question in lists by its shorthand, label and variable name", () => {
    expect(questionChoice({ type: "yes_no", label: "Attacker IP", key: "attacker_ip" })).toBe("YN · Attacker IP (attacker_ip)");
    expect(questionChoice({ type: "heading", label: "Details", key: null })).toBe("HD · Details");
  });
});
