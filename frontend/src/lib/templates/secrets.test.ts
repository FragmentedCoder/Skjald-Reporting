import { describe, expect, it } from "vitest";
import secrets from "../../../../shared/templates/secrets.json";
import { maskedSecret, printed } from "./secrets";

describe("secrets in the PDF", () => {
  it.each(secrets.cases)("$secret prints as $printed", ({ secret, printed: expected }) => {
    expect(printed(secret)).toBe(expected);
    expect(printed(secret, "omit")).toBe("");
  });
});

describe("a secret kept in a report", () => {
  it("is read as masked only when it says so", () => {
    expect(maskedSecret({ masked: true, printed: "So••••••rd" })).toEqual({ masked: true, printed: "So••••••rd" });
    // One the template leaves out of the PDF prints as nothing, and is still filled in.
    expect(maskedSecret({ masked: true, printed: "" })).toEqual({ masked: true, printed: "" });
    expect(maskedSecret({ masked: true })).toEqual({ masked: true, printed: "" });
    for (const other of ["Sommer2026!Fjord", "", null, undefined, { masked: false, printed: "x" }, { printed: "x" }, [true]]) {
      expect(maskedSecret(other)).toBeNull();
    }
  });
});
