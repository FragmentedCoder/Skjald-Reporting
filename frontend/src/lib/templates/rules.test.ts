import { describe, expect, it } from "vitest";
import { Engine } from "#lib/cel/engine.js";
import {
  conditionFromCel,
  conditionToCel,
  shapeOf,
  valueFromCel,
  valueToCel,
  type Condition,
  type Shape,
  type ValueRule,
} from "./rules";

const TYPES: Record<string, string> = {
  "answers.cvss": "double",
  "answers.count": "int",
  "answers.found": "bool",
  "answers.monitored": "bool",
  "answers.title": "string",
  "answers.status": "string",
  "answers.detected": "timestamp",
  "answers.tags": "list<string>",
  "answers.rows": "list<map<string, dyn>>",
};
const SHAPES: Record<string, Shape> = {
  ...Object.fromEntries(Object.entries(TYPES).map(([n, t]) => [n, shapeOf(t)])),
  "row.attempts": "whole",
  "row.ip": "text",
};
const engine = new Engine(TYPES);

const c = (name: string, op: Condition extends never ? never : string, extra: object = {}): Condition =>
  ({ kind: "compare", name, op, ...extra }) as Condition;

const CONDITIONS: [Condition, string][] = [
  [c("answers.cvss", "ge", { value: 9 }), "answers.cvss >= 9.0"],
  [c("answers.cvss", "lt", { value: 4.5 }), "answers.cvss < 4.5"],
  [c("answers.count", "gt", { value: 3 }), "answers.count > 3"],
  [c("answers.cvss", "between", { value: 7, until: 8.9 }), "answers.cvss >= 7.0 && answers.cvss <= 8.9"],
  [c("answers.found", "yes"), "answers.found"],
  [c("answers.found", "no"), "!answers.found"],
  [c("answers.title", "eq", { value: 'Say "hi"' }), 'answers.title == "Say \\"hi\\""'],
  [c("answers.title", "filled"), 'answers.title != ""'],
  [c("answers.title", "empty"), 'answers.title == ""'],
  [c("answers.title", "contains", { value: "VPN" }), 'answers.title.contains("VPN")'],
  [c("answers.title", "starts", { value: "10." }), 'answers.title.startsWith("10.")'],
  [c("answers.title", "matches", { value: "^10\\." }), 're_match(answers.title, "^10\\\\.")'],
  [c("answers.status", "one_of", { values: ["blocked", "monitored"] }), 'answers.status in ["blocked", "monitored"]'],
  [c("answers.detected", "lt", { value: "2026-10-21" }), 'answers.detected < date("2026-10-21")'],
  [c("answers.tags", "includes", { value: "Mail" }), '"Mail" in answers.tags'],
  [c("answers.tags", "excludes", { value: "Mail" }), '!("Mail" in answers.tags)'],
  [c("answers.tags", "some_chosen"), "answers.tags.size() > 0"],
  [c("answers.rows", "no_rows"), "answers.rows.size() == 0"],
  [c("answers.rows", "rows_at_least", { count: 3 }), "answers.rows.size() >= 3"],
  [c("answers.rows", "any_row", { row: c("row.attempts", "gt", { value: 1000 }) }), "answers.rows.exists(row, row.attempts > 1000)"],
  [c("answers.rows", "every_row", { row: c("row.ip", "filled") }), 'answers.rows.all(row, row.ip != "")'],
  [c("answers.rows", "rows_where_at_least", { count: 2, row: c("row.ip", "starts", { value: "10." }) }),
    'answers.rows.filter(row, row.ip.startsWith("10.")).size() >= 2'],
  [{ kind: "all", items: [c("answers.found", "yes"), c("answers.cvss", "ge", { value: 9 })] }, "answers.found && answers.cvss >= 9.0"],
  [{ kind: "any", items: [c("answers.found", "yes"), { kind: "all", items: [c("answers.monitored", "no"), c("answers.count", "ge", { value: 1 })] }] },
    "answers.found || (!answers.monitored && answers.count >= 1)"],
  [{ kind: "one", items: [c("answers.found", "yes"), c("answers.monitored", "yes")] }, "xor(answers.found, answers.monitored)"],
  [{ kind: "one", items: [c("answers.found", "yes"), c("answers.monitored", "yes"), c("answers.count", "eq", { value: 0 })] },
    "[answers.found, answers.monitored, answers.count == 0].exists_one(x, x)"],
  [{ kind: "not", item: { kind: "any", items: [c("answers.found", "yes"), c("answers.monitored", "yes")] } }, "!(answers.found || answers.monitored)"],
  [{ kind: "all", items: [c("answers.cvss", "between", { value: 1, until: 2 }), c("answers.found", "yes")] },
    "answers.cvss >= 1.0 && answers.cvss <= 2.0 && answers.found"],
  [{ kind: "any", items: [c("answers.cvss", "between", { value: 1, until: 2 }), c("answers.found", "yes")] },
    "(answers.cvss >= 1.0 && answers.cvss <= 2.0) || answers.found"],
];

describe("conditions", () => {
  it.each(CONDITIONS)("%j is %s, and reads back", (condition, cel) => {
    expect(conditionToCel(condition, SHAPES)).toBe(cel);
    expect(engine.check(cel)).toBe("bool");
    expect(conditionFromCel(cel, SHAPES)).toEqual(condition);
  });

  it("reads back what it wrote, whatever the spacing", () => {
    expect(conditionFromCel("answers.found&&answers.cvss   >= 9.0", SHAPES)).toBeNull();
    expect(conditionFromCel("answers.found &&\n  answers.cvss >= 9.0", SHAPES)).toEqual(CONDITIONS[22][0]);
  });

  it.each([
    "answers.cvss * 2.0 > 9.0",
    "answers.title.size() > 3",
    'lookup("severity", answers.title) == "Kritisk"',
    "answers.cvss >= 9", // 9 rather than 9.0 isn't what the editor writes
    "answers.rows.exists(r, r.attempts > 1)",
    "(answers.found)",
    "not even CEL (",
  ])("leaves %s as text", (cel) => {
    expect(conditionFromCel(cel, SHAPES)).toBeNull();
  });
});

const VALUES: [ValueRule, Shape, string][] = [
  [{ kind: "fixed", value: "Low" }, "text", '"Low"'],
  [{ kind: "fixed", value: 2 }, "number", "2.0"],
  [{ kind: "if", branches: [{ when: c("answers.cvss", "ge", { value: 9 }), value: "Critical" }, { when: c("answers.cvss", "ge", { value: 7 }), value: "High" }], otherwise: "Lower" },
    "text", 'answers.cvss >= 9.0 ? "Critical" : answers.cvss >= 7.0 ? "High" : "Lower"'],
  [{ kind: "if", branches: [{ when: { kind: "any", items: [c("answers.found", "yes"), c("answers.monitored", "yes")] }, value: "critical" }], otherwise: "info" },
    "text", 'answers.found || answers.monitored ? "critical" : "info"'],
  [{ kind: "switch", name: "answers.status", cases: [{ match: "blocked", value: "Blocked at the firewall" }, { match: "monitored", value: "Watched" }], otherwise: "Unknown" },
    "text", 'switch(answers.status, {"blocked": "Blocked at the firewall", "monitored": "Watched"}, "Unknown")'],
  [{ kind: "switch", name: "answers.count", cases: [{ match: 1, value: "One" }], otherwise: "Several" },
    "text", 'switch(answers.count, {1: "One"}, "Several")'],
  [{ kind: "switch", name: "answers.status", cases: [{ match: "blocked", value: 1.5 }], otherwise: 0 },
    "number", 'switch(answers.status, {"blocked": 1.5}, 0.0)'],
  [{ kind: "if", branches: [{ when: c("answers.found", "yes"), value: true }], otherwise: false }, "bool", "answers.found ? true : false"],
];

describe("values", () => {
  it.each(VALUES)("%j is %s, and reads back", (rule, shape, cel) => {
    expect(valueToCel(rule, shape, SHAPES)).toBe(cel);
    expect(engine.check(cel)).toBe({ text: "string", number: "double", bool: "bool" }[shape as string]);
    expect(valueFromCel(cel, shape, SHAPES)).toEqual(rule);
  });

  it("leaves other expressions as text", () => {
    expect(valueFromCel('format_date(answers.detected, "d MMMM")', "text", SHAPES)).toBeNull();
    expect(valueFromCel('answers.found ? answers.title : "none"', "text", SHAPES)).toBeNull();
  });
});
