// Template expressions in the browser, against the files both engines share:
// shared/cel/cases.json and the examples in shared/cel/functions.json run here on
// cel-js and on the server on cel-expr-python (backend/tests/test_cel.py).
import { describe, expect, it } from "vitest";
import cases from "../../../../shared/cel/cases.json";
import { Engine, ExpressionError, parseType, typeText, validate } from "./engine";
import { renameReference, tokenize, LexError } from "./lexer";
import { browserOverloads, FUNCTIONS, implementations, LOCALES, type Table } from "./library";

interface Case {
  id: string;
  need: string;
  expr: string;
  declare: Record<string, string>;
  vars: Record<string, unknown>;
  options?: { timezone?: string; language?: string };
  expect?: unknown;
  type?: string;
  error?: { kind: string; message?: string };
  references?: string[];
  time_limit_ms?: number;
}

const TABLES = cases.tables as Record<string, Table>;
const CASES = cases.cases as Case[];

function asJson(value: unknown): unknown {
  if (value instanceof Date) return { timestamp: value.toISOString().replace(/\.\d{3}Z$/, "Z") };
  if (typeof value === "bigint") return Number(value);
  if (Array.isArray(value)) return value.map(asJson);
  if (value instanceof Map) return Object.fromEntries([...value].map(([k, v]) => [String(k), asJson(v)]));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, asJson(v)]));
  return value;
}

function typeOf(value: unknown): string {
  if (typeof value === "bigint") return "int";
  if (typeof value === "number") return "double";
  if (typeof value === "boolean") return "bool";
  if (value instanceof Date) return "timestamp";
  return typeof value;
}

function same(actual: unknown, expected: unknown): boolean {
  if (typeof expected === "number" && typeof actual === "number") {
    return Math.abs(actual - expected) <= 1e-12 * Math.max(1, Math.abs(expected));
  }
  if (Array.isArray(expected)) {
    return Array.isArray(actual) && actual.length === expected.length && expected.every((e, i) => same(actual[i], e));
  }
  if (expected && typeof expected === "object") {
    if (!actual || typeof actual !== "object") return false;
    const keys = Object.keys(expected);
    return keys.length === Object.keys(actual).length && keys.every((k) => same((actual as Record<string, unknown>)[k], (expected as Record<string, unknown>)[k]));
  }
  return actual === expected;
}

const engineFor = (c: Case) =>
  new Engine(c.declare, { timezone: c.options?.timezone, language: c.options?.language, tables: TABLES });

describe("shared cases", () => {
  it.each(CASES)("$id: $need", (c) => {
    const engine = engineFor(c);
    if (c.error) {
      let caught: unknown;
      try {
        engine.evaluateRaw(c.expr, c.vars);
      } catch (error) {
        caught = error;
      }
      expect(caught).toBeInstanceOf(ExpressionError);
      const error = caught as ExpressionError;
      expect(error.kind, error.message).toBe(c.error.kind);
      if (c.error.message) expect(error.message).toBe(c.error.message);
      return;
    }
    const start = performance.now();
    const value = engine.evaluateRaw(c.expr, c.vars);
    const elapsed = performance.now() - start;
    expect(same(asJson(value), c.expect), JSON.stringify(asJson(value))).toBe(true);
    if (c.type) expect(typeOf(value)).toBe(c.type);
    if (c.time_limit_ms) expect(elapsed).toBeLessThan(c.time_limit_ms);
    if (c.references) expect(engine.references(c.expr)).toEqual(c.references);
  });
});

describe("function examples", () => {
  const examples = FUNCTIONS.flatMap((f) => f.examples.map((example) => ({ name: f.name, ...example })));
  it.each(examples)("$expr", ({ expr, result }) => {
    expect(same(asJson(new Engine({}, { tables: TABLES }).evaluateRaw(expr, {})), result)).toBe(true);
  });
});

describe("the library", () => {
  it("implements every overload the browser adds to cel-js, and nothing else", () => {
    const impls = implementations({ zone: "UTC", locale: LOCALES.en, tables: {} });
    expect(Object.keys(impls).sort()).toEqual(browserOverloads().map((o) => o.id).sort());
  });
});

describe("the engine", () => {
  it("gives the checked type", () => {
    const engine = new Engine({ "answers.cvss": "double", "answers.rows": "list<map<string, dyn>>", "answers.when": "timestamp" });
    expect(engine.check("answers.cvss >= 9.0")).toBe("bool");
    expect(engine.check('answers.cvss >= 9.0 ? "Critical" : "Lower"')).toBe("string");
    expect(engine.check("answers.rows")).toBe("list<map<string, dyn>>");
    expect(engine.check("answers.when")).toBe("timestamp");
  });

  it("gives missing values the empty value of their type", () => {
    const engine = new Engine({ "answers.n": "int", "answers.when": "timestamp", "answers.tags": "list<string>", "answers.title": "string", "answers.ok": "bool" });
    expect(engine.evaluate('answers.n == 0 && answers.title == "" && !answers.ok && answers.tags.size() == 0', {})).toBe(true);
    expect(engine.evaluate("answers.when", {})).toEqual(new Date(0));
  });

  it("refuses values of the wrong type", () => {
    const engine = new Engine({ "answers.n": "int", "answers.when": "timestamp" });
    for (const values of [{ answers: { n: "7" } }, { answers: { n: 7.5 } }, { answers: { n: true } }, { answers: { when: "2026-10-21T14:30" } }]) {
      expect(() => engine.evaluate("answers.n", values)).toThrow(ExpressionError);
    }
    expect(engine.evaluate("answers.n", { answers: { n: 7 } })).toBe(7);
  });

  it("reads nested names and list functions' own names", () => {
    const declared = new Set(["answers.rows", "customer.custom.sla"]);
    expect(() => validate("answers.rows.map(r, r.n) + [customer.custom.sla]", declared)).not.toThrow();
    expect(() => validate("customer.custom", declared)).toThrow(/customer.custom on its own/);
  });
});

describe("tokens", () => {
  it("splits text, numbers and operators the way the server does", () => {
    const texts = tokenize(`r'a\\' + b"x" + '''q'q''' + "e\\"" 0x1Fu 1.5e-3 .5 7u`).map((t) => t.text);
    expect(texts).toEqual([`r'a\\'`, "+", `b"x"`, "+", `'''q'q'''`, "+", `"e\\""`, "0x1Fu", "1.5e-3", ".5", "7u"]);
    for (const broken of ['"open', "'''open", "a = b", "a # b", '"line\nbreak"']) {
      expect(() => tokenize(broken)).toThrow(LexError);
    }
  });

  it("renames a name wherever it's read, never inside quotes", () => {
    expect(renameReference('answers.cvss >= 9.0 && "answers.cvss" != "" && answers.cvss_old > 1.0', "answers.cvss", "answers.score"))
      .toBe('answers.score >= 9.0 && "answers.cvss" != "" && answers.cvss_old > 1.0');
    expect(renameReference("answers.rows.exists(r, r.ip == answers.rows[0].ip)", "answers.rows", "answers.hosts"))
      .toBe("answers.hosts.exists(r, r.ip == answers.hosts[0].ip)");
    expect(renameReference("answers . cvss > 1.0", "answers.cvss", "answers.score")).toBe("answers.score > 1.0");
    expect(renameReference("x.answers.cvss", "answers.cvss", "answers.score")).toBe("x.answers.cvss");
  });
});

describe("types", () => {
  it("parse the way the server parses them", () => {
    expect(typeText(parseType("map<string,list<map<string, dyn>>>"))).toBe("map<string, list<map<string, dyn>>>");
    for (const bad of ["list", "map<string>", "set<int>", "list<int>>", "Int"]) expect(() => parseType(bad)).toThrow();
  });
});
