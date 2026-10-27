// The builder's checks against the examples the server's tests run too
// (backend/tests/test_template_content.py): the same problems, in the same order.
import { describe, expect, it } from "vitest";
import checks from "../../../../shared/templates/checks.json";
import incident from "../../../../shared/templates/incident.json";
import { check } from "./checks";
import { CONTEXT_ROOTS, declarations } from "./names";
import type { Problem, TemplateContent } from "./types";

interface Case {
  name: string;
  content: TemplateContent;
  library?: Record<string, string>;
  assets?: string[];
  answers: Record<string, string>;
  problems: Problem[];
}

describe("shared checks", () => {
  it.each(checks.cases as unknown as Case[])("$name", (c) => {
    expect(check(c.content, { library: c.library, assets: c.assets })).toEqual(c.problems);
    const own = Object.fromEntries(
      Object.entries(declarations(c.content, c.library)).filter(([name]) => !CONTEXT_ROOTS.has(name.split(".")[0])),
    );
    expect(own).toEqual(c.answers);
  });

  it("finds nothing wrong with the sample template", () => {
    // The sample as written leaves out settings the server fills in; the builder copes.
    expect(check(incident as unknown as TemplateContent)).toEqual([]);
  });
});
