import { describe, expect, it } from "vitest";
import incident from "../../../../shared/templates/incident.json";
import { repeatedColumns, shownAs, type LabelContext } from "./labels";
import { preview, sampleContext, type Shown } from "./preview";
import type { Question, TemplateContent } from "./types";

const options = [{ value: "kritisk", label: "Kritisk" }, { value: "hoej", label: "Høj" }, { value: "lav", label: "Lav" }];
const columns = [
  { key: "title", label: "Title", type: "text", required: false, settings: {} },
  { key: "sev", label: "Severity", type: "dropdown", required: false, settings: { options } },
  { key: "fixed", label: "Fixed", type: "yes_no", required: false, settings: { yes_label: "Fixed", no_label: "Open" } },
];
const question = (type: string, settings: Record<string, unknown>) => ({ type, settings }) as Pick<Question, "type" | "settings">;
const rows = [{ title: "a", sev: "hoej", fixed: true }, { title: "b", sev: "kritisk", fixed: false }, { title: "c", sev: "", fixed: false }];
const context: LabelContext = {
  questions: new Map([
    ["level", question("dropdown", { options })],
    ["areas", question("multi_select", { options, min_selected: null, max_selected: null })],
    ["found", question("yes_no", { yes_label: "Found", no_label: "Not found" })],
    ["plain", question("yes_no", { yes_label: "Yes", no_label: "No" })],
    ["finds", question("repeating", { columns, min_rows: 0, max_rows: 100 })],
    ["title", question("text", {})],
  ]),
  answer: (key) => (key === "finds" ? rows : key === "areas" ? ["lav", "kritisk"] : undefined),
};

describe("a name printed on its own", () => {
  it("prints a choice as its question shows it", () => {
    expect(shownAs("answers.level", "hoej", context)).toBe("Høj");
    expect(shownAs(" answers.level ", "hoej", context)).toBe("Høj");
    expect(shownAs("answers.areas", ["lav", "kritisk"], context)).toEqual(["Lav", "Kritisk"]);
    // Several choices are printed joined, the only way text prints a list.
    expect(shownAs('answers.areas.join(", ")', "lav, kritisk", context)).toBe("Lav, Kritisk");
    expect(shownAs('answers.areas.join(" / ")', "lav / kritisk", context)).toBe("Lav / Kritisk");
    expect(shownAs("answers.areas.join()", "lavkritisk", context)).toBe("LavKritisk");
    // A choice since taken off the question prints as it was kept.
    expect(shownAs("answers.level", "gone", context)).toBe("gone");
    expect(shownAs("answers.title", "hoej", context)).toBe("hoej");
  });

  it("prints Yes and No as the question names them, and in the report's language when it doesn't", () => {
    expect(shownAs("answers.found", true, context)).toBe("Found");
    expect(shownAs("answers.found", false, context)).toBe("Not found");
    expect(shownAs("answers.plain", true, context)).toBe(true);
  });

  it("prints a row's column the same way: the first row's, each repeated section's, and every row's joined", () => {
    expect(shownAs("answers.finds[1].sev", "kritisk", context)).toBe("Kritisk");
    expect(shownAs("answers.finds[0].fixed", true, context)).toBe("Fixed");
    const item = repeatedColumns("answers.finds", context.questions);
    expect(shownAs("item.sev", "hoej", { ...context, item })).toBe("Høj");
    expect(shownAs("item.sev", "hoej", context)).toBe("hoej");
    expect(repeatedColumns('answers.finds.filter(r, r.sev == "hoej")', context.questions)).toBeUndefined();
    expect(shownAs('answers.finds.map(row, row.sev).join(", ")', "hoej, kritisk, ", context)).toBe("Høj, Kritisk, ");
    expect(shownAs('answers.finds.map(r, r.sev).join(" / ")', "hoej / kritisk / ", context)).toBe("Høj / Kritisk / ");
    expect(shownAs('answers.finds.map(row, row.title).join(", ")', "a, b, c", context)).toBe("a, b, c");
  });

  it("leaves anything worked out as it is: rules and calculations go by the value kept", () => {
    expect(shownAs('answers.level + "!"', "hoej!", context)).toBe("hoej!");
    expect(shownAs('answers.level == "hoej"', true, context)).toBe(true);
    expect(shownAs("upperAscii(answers.level)", "HOEJ", context)).toBe("HOEJ");
  });
});

describe("the previews print labels in running text", () => {
  const find = (blocks: Shown[], id: string): Shown | undefined => {
    for (const b of blocks) {
      if (b.id === id) return b;
      const found = find(b.kind === "section" ? b.blocks : [], id);
      if (found) return found;
    }
    return undefined;
  };

  it("in a heading, in a section repeated for each row, and for every row joined", () => {
    const c = structuredClone(incident) as unknown as TemplateContent;
    const first = c.form[0].questions[0];
    c.form[0].questions.push(
      { ...first, id: "q_level", key: "level", type: "dropdown", label: "Level", required: false, settings: { options } },
      { ...first, id: "q_finds", key: "finds", type: "repeating", label: "Findings", required: false, settings: { columns, min_rows: 0, max_rows: 100 } },
    );
    c.layout.push(
      { id: "b_level", kind: "heading", visible_when: 'answers.level == "hoej"', text: 'Level: {{answers.level}} ({{answers.finds.map(row, row.sev).join(", ")}}); first {{answers.finds[0].sev}}' },
      { id: "b_each", kind: "section", visible_when: null, title: "{{item.title}}: {{item.sev}}, {{item.fixed}}", intro: null, new_page: false, numbered: false, landscape: false, repeat_for: "answers.finds", blocks: [
        { id: "b_inner", kind: "heading", visible_when: 'item.sev == "hoej"', text: "Only for {{item.sev}}" },
      ] },
    );
    const answers = { ...c.sample.answers, q_level: "hoej", q_finds: rows.slice(0, 2) };
    const model = preview({ content: c, answers, context: sampleContext(), assets: {}, timezone: "Europe/Copenhagen" });
    expect(model.errors).toEqual([]);
    // The rule still goes by the value kept; the text prints the label.
    expect(find(model.blocks, "b_level")).toMatchObject({ text: "Level: Høj (Høj, Kritisk); first Høj" });
    expect(model.blocks.filter((b) => b.id.startsWith("b_each")).map((b) => (b as { title: string }).title)).toEqual(["a: Høj, Fixed", "b: Kritisk, Open"]);
    expect(find(model.blocks, "b_inner~0")).toMatchObject({ text: "Only for Høj" });
    expect(find(model.blocks, "b_inner~1")).toBeUndefined();
  });
});
