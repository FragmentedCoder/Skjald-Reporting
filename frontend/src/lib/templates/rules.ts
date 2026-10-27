// The visual rule editors' model, and how it becomes CEL and comes back. Rules are
// stored as CEL text only (docs/architecture.md); the editors read a rule back into
// their own form when it's one they could have written, and show the text otherwise.
//
// A condition is groups (all of, any of, exactly one of), NOT, and comparisons of a
// name with a value. A value rule is IF / ELSE IF / ELSE, or SWITCH on one name.

import { Environment } from "@marcbachmann/cel-js";

export type Literal = string | number | boolean;

export type Op =
  | "eq" | "ne" | "lt" | "le" | "gt" | "ge" | "between"
  | "contains" | "starts" | "ends" | "matches" | "empty" | "filled" | "one_of"
  | "yes" | "no"
  | "includes" | "excludes" | "none_chosen" | "some_chosen"
  | "has_rows" | "no_rows" | "rows_at_least" | "any_row" | "every_row" | "rows_where_at_least";

export interface Compare {
  kind: "compare";
  name: string;
  op: Op;
  value?: Literal;
  /** The upper end of between. */
  until?: Literal;
  /** For one of. */
  values?: string[];
  /** For a condition on the rows of a repeating group: the column's comparison. */
  row?: Compare;
  /** For rows_at_least and rows_where_at_least. */
  count?: number;
}

export interface Group {
  kind: "all" | "any" | "one";
  items: Condition[];
}

export interface Not {
  kind: "not";
  item: Condition;
}

export type Condition = Compare | Group | Not;

export interface IfValue {
  kind: "if";
  branches: { when: Condition; value: Literal }[];
  otherwise: Literal;
}

export interface SwitchValue {
  kind: "switch";
  name: string;
  cases: { match: Literal; value: Literal }[];
  otherwise: Literal;
}

export interface FixedValue {
  kind: "fixed";
  value: Literal;
}

export type ValueRule = IfValue | SwitchValue | FixedValue;

/** The kind of value a name holds, as the editors offer comparisons for it. */
export type Shape = "text" | "number" | "whole" | "bool" | "date" | "texts" | "rows" | "other";

export function shapeOf(type: string): Shape {
  switch (type) {
    case "string":
      return "text";
    case "double":
      return "number";
    case "int":
    case "uint":
      return "whole";
    case "bool":
      return "bool";
    case "timestamp":
      return "date";
    case "list<string>":
      return "texts";
    case "list<map<string, dyn>>":
      return "rows";
    case "dyn":
      return "text";
    default:
      return "other";
  }
}

/** The comparisons offered for each shape, in the order the editor lists them. */
export const OPS: Record<Shape, { op: Op; label: string }[]> = {
  text: [
    { op: "eq", label: "is" }, { op: "ne", label: "is not" }, { op: "one_of", label: "is one of" },
    { op: "contains", label: "contains" }, { op: "starts", label: "starts with" }, { op: "ends", label: "ends with" },
    { op: "matches", label: "matches the pattern" }, { op: "filled", label: "is filled in" }, { op: "empty", label: "is empty" },
  ],
  number: [
    { op: "ge", label: "is at least" }, { op: "gt", label: "is more than" }, { op: "le", label: "is at most" },
    { op: "lt", label: "is less than" }, { op: "eq", label: "is" }, { op: "ne", label: "is not" }, { op: "between", label: "is between" },
  ],
  whole: [
    { op: "ge", label: "is at least" }, { op: "gt", label: "is more than" }, { op: "le", label: "is at most" },
    { op: "lt", label: "is less than" }, { op: "eq", label: "is" }, { op: "ne", label: "is not" }, { op: "between", label: "is between" },
  ],
  bool: [{ op: "yes", label: "is yes" }, { op: "no", label: "is no" }],
  date: [
    { op: "lt", label: "is before" }, { op: "le", label: "is on or before" }, { op: "gt", label: "is after" },
    { op: "ge", label: "is on or after" },
  ],
  texts: [
    { op: "includes", label: "includes" }, { op: "excludes", label: "doesn't include" },
    { op: "some_chosen", label: "has something chosen" }, { op: "none_chosen", label: "has nothing chosen" },
  ],
  rows: [
    { op: "has_rows", label: "has rows" }, { op: "no_rows", label: "has no rows" }, { op: "rows_at_least", label: "has at least … rows" },
    { op: "any_row", label: "has a row where" }, { op: "every_row", label: "has every row where" },
    { op: "rows_where_at_least", label: "has at least … rows where" },
  ],
  other: [],
};

/** Whether an op needs no value (is filled in, is yes). */
export const NO_VALUE = new Set<Op>(["empty", "filled", "yes", "no", "has_rows", "no_rows", "some_chosen", "none_chosen"]);

// To CEL

const NUMBERED = /^-?\d+$/;

/** A value written as CEL for a name of this shape: 9 as 9.0 for a decimal, dates as date("…"). */
export function literal(value: Literal | undefined, shape: Shape): string {
  if (shape === "number") {
    const n = Number(value ?? 0);
    const text = Number.isFinite(n) ? String(n) : "0";
    return NUMBERED.test(text) ? `${text}.0` : text;
  }
  if (shape === "whole") return String(Math.trunc(Number(value ?? 0)) || 0);
  if (shape === "bool") return value ? "true" : "false";
  if (shape === "date") return `date(${JSON.stringify(String(value ?? ""))})`;
  return JSON.stringify(String(value ?? ""));
}

const wrap = (text: string, condition: Condition) =>
  condition.kind === "compare" && condition.op !== "between" ? text : `(${text})`;

export function conditionToCel(condition: Condition, shapes: Record<string, Shape>): string {
  switch (condition.kind) {
    case "all":
    case "any": {
      if (!condition.items.length) return condition.kind === "all" ? "true" : "false";
      if (condition.items.length === 1) return conditionToCel(condition.items[0], shapes);
      // A range needs no brackets among other ANDs: it's an AND itself.
      const bare = (item: Condition) => condition.kind === "all" && item.kind === "compare";
      return condition.items
        .map((item) => (bare(item) ? conditionToCel(item, shapes) : wrap(conditionToCel(item, shapes), item)))
        .join(condition.kind === "all" ? " && " : " || ");
    }
    case "one": {
      const items = condition.items.map((item) => conditionToCel(item, shapes));
      if (items.length === 2) return `xor(${items[0]}, ${items[1]})`;
      return `[${items.join(", ")}].exists_one(x, x)`;
    }
    case "not":
      return `!(${conditionToCel(condition.item, shapes)})`;
    case "compare":
      return compareToCel(condition, shapes[condition.name] ?? "text", shapes);
  }
}

function compareToCel(c: Compare, shape: Shape, shapes: Record<string, Shape>): string {
  const n = c.name;
  const v = () => literal(c.value, shape);
  const text = () => literal(c.value, "text");
  switch (c.op) {
    case "eq": return `${n} == ${v()}`;
    case "ne": return `${n} != ${v()}`;
    case "lt": return `${n} < ${v()}`;
    case "le": return `${n} <= ${v()}`;
    case "gt": return `${n} > ${v()}`;
    case "ge": return `${n} >= ${v()}`;
    case "between": return `${n} >= ${v()} && ${n} <= ${literal(c.until, shape)}`;
    case "contains": return `${n}.contains(${text()})`;
    case "starts": return `${n}.startsWith(${text()})`;
    case "ends": return `${n}.endsWith(${text()})`;
    case "matches": return `re_match(${n}, ${text()})`;
    case "empty": return `${n} == ""`;
    case "filled": return `${n} != ""`;
    case "one_of": return `${n} in [${(c.values ?? []).map((x) => JSON.stringify(x)).join(", ")}]`;
    case "yes": return n;
    case "no": return `!${n}`;
    case "includes": return `${text()} in ${n}`;
    case "excludes": return `!(${text()} in ${n})`;
    case "some_chosen":
    case "has_rows": return `${n}.size() > 0`;
    case "none_chosen":
    case "no_rows": return `${n}.size() == 0`;
    case "rows_at_least": return `${n}.size() >= ${Math.max(0, Math.trunc(c.count ?? 1))}`;
    case "any_row":
    case "every_row":
    case "rows_where_at_least": {
      const row = c.row ?? { kind: "compare", name: "row.value", op: "filled" };
      const inner = compareToCel(row, shapes[row.name] ?? "text", shapes);
      if (c.op === "any_row") return `${n}.exists(row, ${inner})`;
      if (c.op === "every_row") return `${n}.all(row, ${inner})`;
      return `${n}.filter(row, ${inner}).size() >= ${Math.max(0, Math.trunc(c.count ?? 1))}`;
    }
  }
}

export function valueToCel(rule: ValueRule, result: Shape, shapes: Record<string, Shape>): string {
  switch (rule.kind) {
    case "fixed":
      return literal(rule.value, result);
    case "if": {
      let text = literal(rule.otherwise, result);
      for (const branch of [...rule.branches].reverse()) {
        text = `${wrapTernary(conditionToCel(branch.when, shapes))} ? ${literal(branch.value, result)} : ${text}`;
      }
      return text;
    }
    case "switch": {
      const key = shapes[rule.name] === "whole" ? "whole" : "text";
      const cases = rule.cases.map((c) => `${literal(c.match, key)}: ${literal(c.value, result)}`).join(", ");
      return `switch(${rule.name}, {${cases}}, ${literal(rule.otherwise, result)})`;
    }
  }
}

// A ternary's condition needs brackets when it holds a ternary of its own; || and &&
// bind tighter than ?:, so they don't.
const wrapTernary = (text: string) => (text.includes("?") ? `(${text})` : text);

// From CEL

interface Node {
  op: string;
  args: unknown;
}

const parser = new Environment({ unlistedVariablesAreDyn: true, homogeneousAggregateLiterals: false });

function parse(expr: string): Node | null {
  try {
    return parser.parse(expr).ast as unknown as Node;
  } catch {
    return null;
  }
}

const isNode = (x: unknown): x is Node => !!x && typeof x === "object" && "op" in x;

/** A dotted name (answers.cvss, row.ip), or null. */
function nameOf(node: unknown): string | null {
  if (!isNode(node)) return null;
  if (node.op === "id") return String(node.args);
  if (node.op === ".") {
    const [object, field] = node.args as [unknown, string];
    const base = nameOf(object);
    return base === null ? null : `${base}.${field}`;
  }
  return null;
}

/** A literal's value, or undefined; date("…") counts, as its text. */
function valueOf(node: unknown): Literal | undefined {
  if (!isNode(node)) return undefined;
  if (node.op === "value") {
    const v = node.args;
    if (typeof v === "bigint") return Number(v);
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return v;
    return undefined;
  }
  if (node.op === "-_") {
    const inner = valueOf(node.args);
    return typeof inner === "number" ? -inner : undefined;
  }
  if (node.op === "call") {
    const [fn, args] = node.args as [string, unknown[]];
    if (fn === "date" && args.length === 1) {
      const inner = valueOf(args[0]);
      return typeof inner === "string" ? inner : undefined;
    }
  }
  return undefined;
}

const COMPARISON: Record<string, Op> = { "==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge" };

function flatten(node: Node, op: string): unknown[] {
  return (node.args as unknown[]).flatMap((child) => (isNode(child) && child.op === op ? flatten(child, op) : [child]));
}

function sizeOf(node: unknown): string | null {
  if (!isNode(node) || node.op !== "rcall") return null;
  const [fn, receiver, args] = node.args as [string, unknown, unknown[]];
  return fn === "size" && args.length === 0 ? nameOf(receiver) : null;
}

function compareFrom(node: Node, shapes: Record<string, Shape>): Compare | null {
  const plain = nameOf(node);
  if (plain !== null) return shapes[plain] === "bool" ? { kind: "compare", name: plain, op: "yes" } : null;
  if (node.op === "!_") {
    const name = nameOf(node.args);
    if (name !== null && shapes[name] === "bool") return { kind: "compare", name, op: "no" };
    const inner = isNode(node.args) ? compareFrom(node.args, shapes) : null;
    if (inner?.op === "includes") return { ...inner, op: "excludes" };
    return null;
  }
  if (node.op in COMPARISON) {
    const [left, right] = node.args as [unknown, unknown];
    const counted = sizeOf(left);
    const count = valueOf(right);
    if (counted !== null && typeof count === "number") {
      const shape = shapes[counted];
      if (node.op === ">" && count === 0) return { kind: "compare", name: counted, op: shape === "texts" ? "some_chosen" : "has_rows" };
      if (node.op === "==" && count === 0) return { kind: "compare", name: counted, op: shape === "texts" ? "none_chosen" : "no_rows" };
      if (node.op === ">=" && shape === "rows") return { kind: "compare", name: counted, op: "rows_at_least", count };
      return null;
    }
    if (isNode(left) && left.op === "rcall" && node.op === ">=" && typeof count === "number") {
      const [fn, receiver, args] = left.args as [string, unknown, unknown[]];
      if (fn === "size" && args.length === 0 && isNode(receiver) && receiver.op === "rcall") {
        const filtered = rowCondition(receiver, "filter", shapes);
        if (filtered) return { ...filtered, op: "rows_where_at_least", count };
      }
      return null;
    }
    const name = nameOf(left);
    const value = valueOf(right);
    if (name === null || value === undefined) return null;
    if (value === "" && node.op === "==") return { kind: "compare", name, op: "empty" };
    if (value === "" && node.op === "!=") return { kind: "compare", name, op: "filled" };
    return { kind: "compare", name, op: COMPARISON[node.op], value };
  }
  if (node.op === "in") {
    const [left, right] = node.args as [unknown, unknown];
    const value = valueOf(left);
    const list = nameOf(right);
    if (typeof value === "string" && list !== null) return { kind: "compare", name: list, op: "includes", value };
    const name = nameOf(left);
    if (name !== null && isNode(right) && right.op === "list") {
      const values = (right.args as unknown[]).map(valueOf);
      if (values.every((x) => typeof x === "string")) return { kind: "compare", name, op: "one_of", values: values as string[] };
    }
    return null;
  }
  if (node.op === "rcall") {
    const [fn] = node.args as [string];
    const ops: Record<string, Op> = { contains: "contains", startsWith: "starts", endsWith: "ends" };
    if (fn in ops) {
      const [, receiver, args] = node.args as [string, unknown, unknown[]];
      const name = nameOf(receiver);
      const value = valueOf(args[0]);
      return name !== null && typeof value === "string" && args.length === 1 ? { kind: "compare", name, op: ops[fn], value } : null;
    }
    if (fn === "exists" || fn === "all") {
      const found = rowCondition(node, fn, shapes);
      return found ? { ...found, op: fn === "exists" ? "any_row" : "every_row" } : null;
    }
    return null;
  }
  if (node.op === "call") {
    const [fn, args] = node.args as [string, unknown[]];
    if (fn === "re_match" && args.length === 2) {
      const name = nameOf(args[0]);
      const value = valueOf(args[1]);
      return name !== null && typeof value === "string" ? { kind: "compare", name, op: "matches", value } : null;
    }
  }
  return null;
}

/** name.exists(row, …), name.all(row, …) or name.filter(row, …) with one column comparison. */
function rowCondition(node: Node, fn: string, shapes: Record<string, Shape>): Compare | null {
  const [called, receiver, args] = node.args as [string, unknown, unknown[]];
  if (called !== fn || args.length !== 2 || nameOf(args[0]) !== "row") return null;
  const name = nameOf(receiver);
  const row = isNode(args[1]) ? compareFrom(args[1], shapes) : null;
  if (name === null || row === null || !row.name.startsWith("row.")) return null;
  return { kind: "compare", name, op: "any_row", row };
}

function conditionFrom(node: Node, shapes: Record<string, Shape>): Condition | null {
  if (node.op === "&&") {
    const all = group("all", flatten(node, "&&"), shapes);
    if (all === null) return null;
    // name >= a && name <= b, side by side: between.
    const items: Condition[] = [];
    for (const item of all.items) {
      const before = items[items.length - 1];
      if (before?.kind === "compare" && item.kind === "compare" && before.op === "ge" && item.op === "le"
          && before.name === item.name && before.value !== undefined) {
        items[items.length - 1] = { kind: "compare", name: item.name, op: "between", value: before.value, until: item.value };
      } else {
        items.push(item);
      }
    }
    return items.length === 1 ? items[0] : { kind: "all", items };
  }
  if (node.op === "||") return group("any", flatten(node, "||"), shapes);
  if (node.op === "call") {
    const [fn, args] = node.args as [string, unknown[]];
    if (fn === "xor" && args.length === 2) return group("one", args, shapes);
  }
  if (node.op === "rcall") {
    const [fn, receiver, args] = node.args as [string, unknown, unknown[]];
    if (fn === "exists_one" && isNode(receiver) && receiver.op === "list" && args.length === 2 && nameOf(args[0]) === "x" && nameOf(args[1]) === "x") {
      return group("one", receiver.args as unknown[], shapes);
    }
  }
  const compared = compareFrom(node, shapes);
  if (compared) return compared;
  if (node.op === "!_" && isNode(node.args)) {
    const inner = conditionFrom(node.args, shapes);
    return inner ? { kind: "not", item: inner } : null;
  }
  return null;
}

function group(kind: Group["kind"], nodes: unknown[], shapes: Record<string, Shape>): Group | null {
  const items: Condition[] = [];
  for (const child of nodes) {
    const item = isNode(child) ? conditionFrom(child, shapes) : null;
    if (item === null) return null;
    items.push(item);
  }
  return { kind, items };
}

/**
 * The condition an expression is, if the visual editor could have written it; else
 * null. Read back strictly: writing it again gives the same text, or it's null.
 */
export function conditionFromCel(expr: string, shapes: Record<string, Shape>): Condition | null {
  const node = parse(expr);
  if (!node) return null;
  const condition = conditionFrom(node, shapes);
  if (condition === null) return null;
  return normalise(conditionToCel(condition, shapes)) === normalise(expr) ? condition : null;
}

export function valueFromCel(expr: string, result: Shape, shapes: Record<string, Shape>): ValueRule | null {
  const node = parse(expr);
  if (!node) return null;
  const rule = valueFrom(node, shapes);
  if (rule === null) return null;
  return normalise(valueToCel(rule, result, shapes)) === normalise(expr) ? rule : null;
}

function valueFrom(node: Node, shapes: Record<string, Shape>): ValueRule | null {
  const fixed = valueOf(node);
  if (fixed !== undefined) return { kind: "fixed", value: fixed };
  if (node.op === "?:") {
    const branches: IfValue["branches"] = [];
    let current: unknown = node;
    while (isNode(current) && current.op === "?:") {
      const [test, yes, no] = current.args as [unknown, unknown, unknown];
      const when = isNode(test) ? conditionFrom(test, shapes) : null;
      const value = valueOf(yes);
      if (when === null || value === undefined) return null;
      branches.push({ when, value });
      current = no;
    }
    const otherwise = valueOf(current);
    return otherwise === undefined ? null : { kind: "if", branches, otherwise };
  }
  if (node.op === "call") {
    const [fn, args] = node.args as [string, unknown[]];
    if (fn === "switch" && args.length === 3 && isNode(args[1]) && args[1].op === "map") {
      const name = nameOf(args[0]);
      const otherwise = valueOf(args[2]);
      const cases = (args[1].args as [unknown, unknown][]).map(([k, v]) => ({ match: valueOf(k), value: valueOf(v) }));
      if (name === null || otherwise === undefined || cases.some((c) => c.match === undefined || c.value === undefined)) return null;
      return { kind: "switch", name, cases: cases as SwitchValue["cases"], otherwise };
    }
  }
  return null;
}

/** The text without layout, so spacing a designer typed doesn't stop a rule reading back. */
function normalise(expr: string): string {
  return expr.replace(/\s+/g, " ").replace(/\(\s/g, "(").replace(/\s\)/g, ")").trim();
}
