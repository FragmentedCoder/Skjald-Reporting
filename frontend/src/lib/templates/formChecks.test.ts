import { describe, expect, it } from "vitest";
import { answerProblem, cellProblem } from "./formChecks";

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
