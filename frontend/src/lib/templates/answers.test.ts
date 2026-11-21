// Answers to typed questions, against the cases the server runs too
// (backend/tests/test_template_answers.py).
import { describe, expect, it } from "vitest";
import cases from "../../../../shared/fields/cases.json";
import { checkAnswer, cvssScore } from "./answers";

interface Case {
  type: string;
  settings: Record<string, unknown>;
  value: string | number;
  message: string | null;
  score?: number;
  severity?: string;
}

describe("answers", () => {
  it.each(cases.cases as Case[])("$type: $value", (c) => {
    expect(checkAnswer(c.type, c.settings, c.value)).toBe(c.message);
    if (c.score !== undefined) expect(cvssScore(String(c.value))).toEqual({ score: c.score, severity: c.severity });
  });

  it("doesn't check empty answers", () => {
    for (const type of ["ip", "hostname", "mac", "email", "phone", "cvss", "text", "number"]) {
      expect(checkAnswer(type, {}, "")).toBeNull();
      expect(checkAnswer(type, {}, null)).toBeNull();
    }
  });

  it("refuses a CVSS vector with a part named as something every object has, without failing", () => {
    for (const part of ["constructor:X", "toString:X", "__proto__:X", "hasOwnProperty:N"]) {
      expect(checkAnswer("cvss", { versions: ["3.1", "4.0"] }, `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H/${part}`)).not.toBeNull();
    }
  });
});
