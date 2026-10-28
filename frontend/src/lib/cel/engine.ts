// Template expressions in the browser: cel-js with Skjald's library, the live
// counterpart of backend/app/cel/engine.py. An Engine is made for one set of declared
// names (answers.cvss: double, ...). Checking an expression runs Skjald's validator
// (the same token rules as the server), then cel-js's type check, then the one thing
// cel-js allows that Google's engine doesn't: comparing a whole number with a decimal.
// Values are converted by their declared type, as the server converts them, and a
// missing value gets its type's empty value. The shared cases hold both sides to the
// same answers.

import { Environment } from "@marcbachmann/cel-js";
import { calls, declaredPrefix, LexError, paths, references, tokenize, type Token } from "./lexer";
import { ALLOWED, BANNED, browserOverloads, celJsType, implementations, LOCALES, type Table } from "./library";

export const MAX_LENGTH = 2000;
export const DEFAULT_ZONE = "Europe/Copenhagen";
const EPOCH = new Date(0);

/** A type in words: bool is "yes or no", list<string> "a list". */
export function human(type: string): string {
  if (type.startsWith("list")) return "a list";
  if (type.startsWith("map")) return "a map";
  const words: Record<string, string> = {
    bool: "yes or no",
    string: "text",
    int: "a whole number",
    uint: "a whole number",
    double: "a decimal number",
    timestamp: "a date and time",
    "google.protobuf.timestamp": "a date and time",
    duration: "a length of time",
    "google.protobuf.duration": "a length of time",
    null: "nothing",
    dyn: "any value",
    null_type: "nothing",
  };
  return words[type.toLowerCase()] ?? type;
}

const and = (words: string[]) =>
  words.length === 1 ? words[0] : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;

// The engines word their errors differently; the common ones are said the same way on
// both sides (backend/app/cel/engine.py), from the facts each engine gives. cel-js
// would compare whole numbers with decimals, which Google's engine refuses, so the
// browser refuses those comparisons itself.
export const MIXED_COMPARISON =
  "A whole number can't be compared with a decimal: write 9.0 rather than 9, or convert one side with double() or int().";
export const MIXED_ARITHMETIC =
  "Whole numbers and decimals can't be mixed in a sum: write 9.0 rather than 9, or convert one side with double() or int().";
export const LOGICAL = "AND (&&) and OR (||) need yes or no on both sides.";
const NUMBERS = new Set(["int", "uint", "double"]);

export const unknownName = (name: string) => `${name.split(".")[0]} isn't a name this template has.`;

export const branches = (first: string, second: string) =>
  `Both results of an IF / ELSE must be the same kind of value: here ${human(first)} and ${human(second)}.`;

export function operatorProblem(op: string, types: string[]): string {
  if (op === "&&" || op === "||") return LOGICAL;
  if (types.length === 2 && types.every((t) => NUMBERS.has(t)) && (types[0] === "double") !== (types[1] === "double")) {
    return "+-*/%".includes(op) ? MIXED_ARITHMETIC : MIXED_COMPARISON;
  }
  if (types.length === 1) return `${op} doesn't work with ${human(types[0])}.`;
  return `${op} doesn't work with ${human(types[0])} and ${human(types[1])}.`;
}

export const functionProblem = (name: string, types: string[]) => `${name}() can't take ${and(types.map(human))}.`;

function splitTypes(text: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let current = "";
  for (const c of text) {
    if (c === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
      continue;
    }
    if (c === "<" || c === "(") depth += 1;
    if (c === ">" || c === ")") depth -= 1;
    current += c;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

export type Kind = "invalid" | "compile" | "runtime";

export class ExpressionError extends Error {
  constructor(
    readonly kind: Kind,
    message: string,
  ) {
    super(message);
  }
}

export interface EngineOptions {
  timezone?: string;
  language?: string;
  tables?: Record<string, Table>;
}

// Types, written as in shared/cel/functions.json.

export interface TypeSpec {
  name: string;
  args: TypeSpec[];
}

const SCALARS = new Set(["bool", "int", "uint", "double", "string", "bytes", "timestamp", "duration", "dyn", "null"]);

export function parseType(text: string): TypeSpec {
  let rest = text.replaceAll(" ", "");
  const parse = (): TypeSpec => {
    const match = /^[a-z]+/.exec(rest);
    if (!match) throw new Error(`Expected a type at '${rest}'.`);
    const name = match[0];
    rest = rest.slice(name.length);
    if (SCALARS.has(name)) return { name, args: [] };
    const arity = ({ list: 1, map: 2 } as Record<string, number>)[name];
    if (!arity || !rest.startsWith("<")) throw new Error(`Unknown type '${name}'.`);
    rest = rest.slice(1);
    const args: TypeSpec[] = [];
    for (let i = 0; i < arity; i++) {
      args.push(parse());
      const expected = i === arity - 1 ? ">" : ",";
      if (!rest.startsWith(expected)) throw new Error(`Expected '${expected}' in a ${name} type.`);
      rest = rest.slice(1);
    }
    return { name, args };
  };
  const spec = parse();
  if (rest) throw new Error(`Unexpected '${rest}' in the type '${text}'.`);
  return spec;
}

export function typeText(spec: TypeSpec): string {
  return spec.args.length ? `${spec.name}<${spec.args.map(typeText).join(", ")}>` : spec.name;
}

// Validation

/** Skjald's own checks, the same on both sides; the engine's type check follows. */
export function validate(expr: string, declared: ReadonlySet<string>): Token[] {
  if (expr.length > MAX_LENGTH) {
    throw new ExpressionError("invalid", `Expressions are limited to ${MAX_LENGTH.toLocaleString("en")} characters.`);
  }
  let tokens: Token[];
  try {
    tokens = tokenize(expr);
  } catch (error) {
    if (error instanceof LexError) throw new ExpressionError("compile", error.message);
    throw error;
  }
  for (const call of calls(tokens)) {
    if (Object.hasOwn(BANNED, call.name)) throw new ExpressionError("invalid", BANNED[call.name]);
    if (!ALLOWED.has(call.name)) throw new ExpressionError("invalid", `${call.name}() isn't a function Skjald knows.`);
  }
  const roots = new Set([...declared].map((name) => name.split(".")[0]));
  for (const path of paths(tokens)) {
    if (declaredPrefix(path, declared) !== null) continue;
    const dotted = path.names.join(".");
    const inside = [...declared].filter((name) => name.startsWith(dotted + ".")).sort();
    if (inside.length) {
      throw new ExpressionError(
        "invalid",
        `${dotted} on its own isn't a value: use one name inside it, such as ${inside[0]}.`,
      );
    }
    if (path.names.length > 1 && roots.has(path.names[0])) {
      throw new ExpressionError("invalid", `${dotted} isn't a name this template has.`);
    }
  }
  return tokens;
}

function engineMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  const first = raw.split("\n")[0];
  let match = /^Unknown variable: (\S+)/.exec(first);
  if (match) return unknownName(match[1]);
  if (first.startsWith("Logical operator requires bool operands")) return LOGICAL;
  match = /^Ternary branches must have the same type, got '(.+)' and '(.+)'$/.exec(first);
  if (match) return branches(match[1], match[2]);
  match = /^no such overload: (.+?) (==|!=|<=|>=|<|>|\+|-|\*|\/|%|in) (.+)$/.exec(first);
  if (match) return operatorProblem(match[2], [match[1], match[3]]);
  match = /^no such overload: ([!-])(.+)$/.exec(first);
  if (match) return operatorProblem(match[1], [match[2]]);
  match = /^found no matching overload for '(?:(.+)\.)?([A-Za-z_]\w*)\((.*)\)'$/.exec(first);
  if (match) return functionProblem(match[2], [...(match[1] ? [match[1]] : []), ...splitTypes(match[3])]);
  return first;
}

interface Node {
  op: string;
  args: unknown;
  checkedType?: { name: string };
}

/** Whether a checked syntax tree compares a whole number with a decimal anywhere. */
function comparesMixedNumbers(node: unknown): boolean {
  if (Array.isArray(node)) return node.some(comparesMixedNumbers);
  if (!node || typeof node !== "object" || !("op" in node)) return false;
  const { op, args } = node as Node;
  if (["<", "<=", ">", ">="].includes(op) && Array.isArray(args)) {
    const [left, right] = (args as Node[]).map((a) => a?.checkedType?.name ?? "dyn");
    if (NUMBERS.has(left) && NUMBERS.has(right) && (left === "double") !== (right === "double")) {
      return true;
    }
  }
  return comparesMixedNumbers(args);
}

// Values

function empty(spec: TypeSpec): unknown {
  switch (spec.name) {
    case "bool":
      return false;
    case "int":
    case "uint":
      return 0n;
    case "double":
      return 0;
    case "string":
      return "";
    case "timestamp":
      return EPOCH;
    case "list":
      return [];
    case "map":
      return {};
    default:
      return null;
  }
}

const OFFSET = /(Z|[+-]\d{2}:?\d{2})$/i;

/** A plain dynamic value: whole numbers become CEL ints, as JSON numbers do on the server. */
function dynamic(value: unknown): unknown {
  if (typeof value === "number" && Number.isInteger(value)) return BigInt(value);
  if (Array.isArray(value)) return value.map(dynamic);
  if (value && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, dynamic(v)]));
  }
  return value;
}

/** A plain value (as JSON would carry it) converted to its declared type. */
export function toCel(value: unknown, spec: TypeSpec, name: string): unknown {
  if (value === null || value === undefined) return empty(spec);
  const wrong = () => new ExpressionError("runtime", `${name} should be ${typeText(spec)}, not ${JSON.stringify(value)}.`);
  switch (spec.name) {
    case "bool":
      if (typeof value !== "boolean") throw wrong();
      return value;
    case "int":
    case "uint":
      if (typeof value === "bigint") return value;
      if (typeof value !== "number" || !Number.isInteger(value)) throw wrong();
      return BigInt(value);
    case "double":
      if (typeof value === "bigint") return Number(value);
      if (typeof value !== "number") throw wrong();
      return value;
    case "string":
      if (typeof value !== "string") throw wrong();
      return value;
    case "timestamp": {
      if (value instanceof Date) return value;
      if (typeof value !== "string" || !OFFSET.test(value)) throw wrong();
      const parsed = new Date(value);
      if (Number.isNaN(parsed.getTime())) throw wrong();
      return parsed;
    }
    case "list":
      if (!Array.isArray(value)) throw wrong();
      return value.map((item) => toCel(item, spec.args[0], name));
    case "map":
      if (typeof value !== "object" || Array.isArray(value)) throw wrong();
      return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toCel(v, spec.args[1], name)]));
    default:
      return dynamic(value);
  }
}

function find(values: Record<string, unknown>, dotted: string): unknown {
  let current: unknown = values;
  for (const part of dotted.split(".")) {
    if (!current || typeof current !== "object" || !Object.hasOwn(current, part)) return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

/** A CEL value as plain JavaScript: whole numbers as numbers, maps as objects. */
export function plain(value: unknown): unknown {
  if (typeof value === "bigint") return Number(value);
  if (Array.isArray(value)) return value.map(plain);
  if (value instanceof Map) return Object.fromEntries([...value].map(([k, v]) => [String(k), plain(v)]));
  if (value && typeof value === "object" && !(value instanceof Date)) {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, plain(v)]));
  }
  return value;
}

interface Tree {
  [name: string]: Tree | TypeSpec;
}

const isSpec = (node: Tree | TypeSpec): node is TypeSpec => typeof (node as TypeSpec).name === "string" && Array.isArray((node as TypeSpec).args);

/** Checks and evaluates expressions over one set of declared names. */
export class Engine {
  readonly declarations: Map<string, TypeSpec>;
  readonly #declared: Set<string>;
  readonly #env: Environment;

  constructor(declarations: Record<string, string>, options: EngineOptions = {}) {
    this.declarations = new Map(Object.entries(declarations).map(([name, text]) => [name, parseType(text)]));
    this.#declared = new Set(this.declarations.keys());
    const locale = LOCALES[options.language ?? "en"];
    if (!locale) throw new Error(`No locale for '${options.language}'.`);
    const impls = implementations({ zone: options.timezone ?? DEFAULT_ZONE, locale, tables: options.tables ?? {} });
    let env = new Environment({ homogeneousAggregateLiterals: false });
    for (const overload of browserOverloads()) {
      env = env.registerFunction(celJsType(overload.signature), impls[overload.id] as (...args: unknown[]) => unknown);
    }
    // Names with dots become object types in cel-js: answers is a type whose fields
    // are the template's questions, customer.custom one inside customer, and so on.
    const tree: Tree = {};
    for (const [name, spec] of this.declarations) {
      const parts = name.split(".");
      let node = tree;
      parts.slice(0, -1).forEach((part) => (node = (node[part] ??= {}) as Tree));
      node[parts[parts.length - 1]] = spec;
    }
    const typeFor = (node: Tree | TypeSpec, path: string): string => {
      if (isSpec(node)) return celJsType(typeText(node));
      const typeName = `Skjald_${path.replaceAll(".", "_")}`;
      const fields = Object.fromEntries(Object.entries(node).map(([k, v]) => [k, typeFor(v, `${path}.${k}`)]));
      env = env.registerType(typeName, { fields });
      return typeName;
    };
    for (const [root, node] of Object.entries(tree)) env = env.registerVariable(root, typeFor(node, root));
    this.#env = env;
  }

  #compile(expr: string) {
    validate(expr, this.#declared);
    let parsed;
    try {
      parsed = this.#env.parse(expr);
    } catch (error) {
      throw new ExpressionError("compile", engineMessage(error));
    }
    const checked = parsed.check();
    if (!checked.valid) throw new ExpressionError("compile", engineMessage(checked.error));
    if (comparesMixedNumbers(parsed.ast)) throw new ExpressionError("compile", MIXED_COMPARISON);
    return { parsed, type: checked.type ?? "dyn" };
  }

  /** The type the expression gives, if Skjald will run it; else ExpressionError. */
  check(expr: string): string {
    return this.#compile(expr).type.replace("google.protobuf.Timestamp", "timestamp").replace("google.protobuf.Duration", "duration");
  }

  /** The declared names the expression reads. */
  references(expr: string): string[] {
    return references(validate(expr, this.#declared), this.#declared);
  }

  /** The value as cel-js gives it: whole numbers as bigint. */
  evaluateRaw(expr: string, values: Record<string, unknown>): unknown {
    const { parsed } = this.#compile(expr);
    const data: Record<string, unknown> = {};
    for (const [name, spec] of this.declarations) {
      const parts = name.split(".");
      let node = data;
      parts.slice(0, -1).forEach((part) => (node = (node[part] ??= {}) as Record<string, unknown>));
      node[parts[parts.length - 1]] = toCel(find(values, name), spec, name);
    }
    try {
      return parsed(data);
    } catch (error) {
      throw new ExpressionError("runtime", engineMessage(error));
    }
  }

  evaluate(expr: string, values: Record<string, unknown>): unknown {
    return plain(this.evaluateRaw(expr, values));
  }
}
