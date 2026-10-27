import { describe, expect, it } from "vitest";
import secrets from "../../../../shared/templates/secrets.json";
import { printed } from "./secrets";

describe("secrets in the PDF", () => {
  it.each(secrets.cases)("$secret prints as $printed", ({ secret, printed: expected }) => {
    expect(printed(secret)).toBe(expected);
    expect(printed(secret, "omit")).toBe("");
  });
});
