// A report's form for a set of answers, against the cases the server runs too
// (backend/tests/test_report_form.py): what expressions read, what questions start as,
// what's hidden, required or refused, and what keeps the report from going for review.
import { describe, expect, it } from "vitest";
import shared from "../../../../shared/reports/form.json";
import type { Table } from "#lib/cel/library.js";
import { FIELD_TYPES } from "./fields";
import { missingAnswers, type Missing } from "./formChecks";
import { preview, sampleContext } from "./preview";
import { questionsOf, type Step, type TemplateContent } from "./types";

interface Case {
  name: string;
  language?: string;
  timezone?: string;
  form: Step[];
  answers: Record<string, unknown>;
  context?: Record<string, Record<string, unknown>>;
  library?: { names: Record<string, string>; values: Record<string, unknown>; tables: Record<string, Table> };
  expect: {
    hidden: string[];
    required: string[];
    invalid: Record<string, string>;
    values: Record<string, unknown>;
    defaults: Record<string, unknown>;
    missing: Missing[];
    errors: { element: string; message?: string }[];
  };
}

describe("a report's form, as the server works it out too", () => {
  it.each(shared.cases as unknown as Case[])("$name", (c) => {
    const content = { schema: 1, settings: { language: c.language ?? "en" }, form: c.form, layout: [], sample: { answers: {} } } as unknown as TemplateContent;
    const context = sampleContext();
    for (const [group, values] of Object.entries(c.context ?? {})) Object.assign(context[group], values);
    const model = preview({ content, answers: c.answers, context, library: c.library, assets: {}, timezone: c.timezone ?? "Europe/Copenhagen" });

    // As JSON carries them: a moment as ISO text in UTC. A date question's own answer
    // is read here as it's kept, which may be with an offset; the server gives every
    // moment the one way.
    const values = JSON.parse(JSON.stringify(model.values)) as Record<string, unknown>;
    for (const q of questionsOf(content)) {
      const kept = q.key ? values[q.key] : null;
      if (q.type === "datetime" && q.key && typeof kept === "string") values[q.key] = new Date(kept).toISOString();
    }
    expect(values).toEqual(c.expect.values);
    expect(JSON.parse(JSON.stringify(model.defaults))).toEqual(c.expect.defaults);
    expect(model.formHidden).toEqual(c.expect.hidden);
    expect(model.formRequired).toEqual(c.expect.required);
    expect(Object.fromEntries(model.invalid.map((i) => [i.id, i.message]))).toEqual(c.expect.invalid);
    expect(missingAnswers(content, model, c.answers)).toEqual(c.expect.missing);
    // Which expressions fail, and in Skjald's own sentences where they're its own.
    expect(model.errors.map((e) => e.element)).toEqual(c.expect.errors.map((e) => e.element));
    c.expect.errors.forEach((e, i) => {
      if (e.message !== undefined) expect(model.errors[i].message).toBe(e.message);
    });
  });

  it("covers every kind of question", () => {
    const kinds = new Set((shared.cases as unknown as Case[]).flatMap((c) => c.form.flatMap((s) => s.questions.map((q) => q.type))));
    expect([...kinds].sort()).toEqual(Object.keys(FIELD_TYPES).sort());
  });
});
