import { describe, expect, it } from "vitest";
import { answerProblem, cellProblem, missingAnswers } from "./formChecks";
import type { Question, Step } from "./types";

const column = (key: string, type: string, more: Record<string, unknown> = {}) => ({ key, label: key[0].toUpperCase() + key.slice(1), type, required: false, settings: {}, ...more });

describe("what keeps an answer from being sent", () => {
  it("is how many are chosen, for several choices", () => {
    const settings = { options: [{ value: "a", label: "A" }, { value: "b", label: "B" }, { value: "c", label: "C" }], min_selected: 2, max_selected: 2 };
    expect(answerProblem({ type: "multi_select", settings }, ["a"])).toBe("Choose at least 2.");
    expect(answerProblem({ type: "multi_select", settings }, ["a", "b", "c"])).toBe("Choose at most 2.");
    expect(answerProblem({ type: "multi_select", settings }, ["a", "b"])).toBeNull();
    // Nothing chosen at all is for "required" to say.
    expect(answerProblem({ type: "multi_select", settings }, null)).toBeNull();
  });

  it("is too few rows, a required cell left empty, or a cell that fails its own check", () => {
    const settings = { columns: [column("address", "ip", { required: true, settings: { versions: "any", cidr: "no" } }), column("port", "number", { settings: { whole: true, min: 1, max: 65535 } })], min_rows: 2, max_rows: 5 };
    const group = { type: "repeating", settings };
    expect(answerProblem(group, [])).toBe("Add at least 2 rows.");
    expect(answerProblem(group, [{ address: "198.51.100.1", port: 443 }])).toBe("Add at least 2 rows.");
    expect(answerProblem(group, [{ address: "198.51.100.1", port: 443 }, { address: null, port: 80 }])).toBe("Row 2, Address: This is required.");
    expect(answerProblem(group, [{ address: "198.51.100.1", port: 443 }, { address: "not an address", port: 80 }])).toMatch(/^Row 2, Address: /);
    expect(answerProblem(group, [{ address: "198.51.100.1", port: 443 }, { address: "198.51.100.2", port: 70000 }])).toBe("Row 2, Port: Enter a number from 1 to 65535.");
    expect(answerProblem(group, [{ address: "198.51.100.1", port: 443 }, { address: "198.51.100.2", port: null }])).toBeNull();
  });

  it("names a table's row by its heading, and counts rows not written yet", () => {
    const settings = { rows: [{ key: "mon", label: "Monday" }, { key: "tue", label: "Tuesday" }], columns: [column("hours", "number", { required: true })] };
    expect(answerProblem({ type: "table", settings }, [{ hours: 7 }])).toBe("Tuesday, Hours: This is required.");
    expect(answerProblem({ type: "table", settings }, [{ hours: 7 }, { hours: 8 }])).toBeNull();
  });

  it("is the answer's own check otherwise, a CVSS vector's included", () => {
    expect(answerProblem({ type: "cvss", settings: { versions: ["3.1"] } }, { vector: "CVSS:3.1/AV:N" })).not.toBeNull();
    expect(answerProblem({ type: "cvss", settings: { versions: ["3.1"] } }, null)).toBeNull();
    expect(answerProblem({ type: "email", settings: {} }, "not an address")).not.toBeNull();
    expect(cellProblem(column("mail", "email"), "")).toBeNull();
  });
});

describe("what keeps a report from going for review", () => {
  const question = (id: string, type: string, more: Partial<Question> = {}): Question =>
    ({ id, key: id.slice(2), type, label: id, help: "", required: false, required_when: null, visible_when: null, default: null, valid_when: null, valid_message: "", value: null, settings: {}, ...more });
  const step = (id: string, questions: Question[]): Step => ({ id, title: id, help: "", visible_when: null, questions });
  const form = [
    step("s_one", [question("q_name", "text"), question("q_part", "heading"), question("q_mail", "email"), question("q_sum", "calculated")]),
    step("s_two", [question("q_when", "datetime"), question("q_score", "cvss")]),
  ];
  type Worked = NonNullable<Parameters<typeof missingAnswers>[1]>;
  const model = (more: Partial<Worked> = {}): Worked => ({ formHidden: [], formRequired: [], invalid: [], defaults: {}, ...more });

  it("is each shown question's own problem, then its rule's, then that it's required and empty", () => {
    const worked = model({ formRequired: ["q_name", "q_part", "q_mail", "q_sum", "q_when", "q_score"], invalid: [{ id: "q_name", message: "Write the whole name." }, { id: "q_mail", message: "Not this one." }] });
    expect(missingAnswers({ form }, worked, { q_name: "Ada", q_mail: "not an address", q_score: { vector: "", score: 0, severity: "" } })).toEqual([
      { step: "s_one", question: "q_name", message: "Write the whole name." },
      { step: "s_one", question: "q_mail", message: "Enter an email address, such as name@fjordvik.example." },
      { step: "s_two", question: "q_when", message: "is required." },
      { step: "s_two", question: "q_score", message: "is required." },
    ]);
  });

  it("leaves out what the form hides, and counts a question not answered yet as what it starts as", () => {
    const worked = model({ formHidden: ["s_two", "q_mail"], formRequired: ["q_name", "q_mail", "q_when"], defaults: { q_name: "Ada" } });
    expect(missingAnswers({ form }, worked, {})).toEqual([]);
    // Cleared on purpose, it's empty whatever it starts as.
    expect(missingAnswers({ form }, worked, { q_name: null })).toEqual([{ step: "s_one", question: "q_name", message: "is required." }]);
  });

  it("still says each answer's own problem before the form is worked out", () => {
    expect(missingAnswers({ form }, null, { q_mail: "not an address" })).toEqual([
      { step: "s_one", question: "q_mail", message: "Enter an email address, such as name@fjordvik.example." },
    ]);
  });
});
