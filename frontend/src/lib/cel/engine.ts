// Template expressions in the browser: cel-js with Skjald's library, the live
// counterpart of backend/app/cel/engine.py. An Engine is made for one set of declared
// names (answers.cvss: double, ...). Checking an expression runs Skjald's validator
// (the same token and syntax rules as the server: lexer.ts, reader.ts), then cel-js's
// type check, then the one thing cel-js allows that Google's engine doesn't: comparing
// a whole number with a decimal. Values are converted by their declared type, as the
// server converts them, and a missing value gets its type's empty value.
//
// The two engines must take the same expressions and give the same answers, so the
// functions they disagree on are Skjald's own on both sides (library.ts), under names
// an expression is rewritten to before cel-js sees it. The shared cases hold both
// sides to the same answers.

import { Environment } from "@marcbachmann/cel-js";
import { formatDate } from "./dates";
import { calls, characters, declaredPrefix, LexError, paths, references, tokenize, type Token } from "./lexer";
import {
  ALIAS, ALIASED, aliased, ALLOWED, BANNED, browserOverloads, celJsType, dateFrom, forms, FUNCTIONS, implementations, LOCALES, regex,
  replacementParts, type Table,
} from "./library";
import { read, RESERVED, TOO_DEEP, Unreadable, unquote, type Call, type Shape } from "./reader";

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
  words.length < 2 ? (words[0] ?? "nothing") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;

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

const unaliased = (name: string) => (name.startsWith(ALIAS) ? name.slice(ALIAS.length) : name);

export const functionProblem = (name: string, types: string[]) => `${unaliased(name)}() can't take ${and(types.map(human))}.`;

export const LIST_PICK =
  "An item of a list is picked by its number, as in answers.rows[0]: to read a name from every row, use map(), exists(), all() or filter().";

/** What's wrong with reading .name or [0] from something that has no parts. */
export const pickProblem = (type: string) =>
  type.startsWith("list") ? LIST_PICK : `Nothing can be picked out of ${human(type)}: only a list, a row or a map has parts.`;

export const keyProblem = (key: string, given: string) => `This map's items are picked by ${human(key)}, not by ${human(given)}.`;

export const conditionProblem = (type: string) => `An IF needs yes or no before its question mark, but this is ${human(type)}.`;

export const ruleProblem = (name: string, type: string) => `The rule in ${name}() must give yes or no, but this gives ${human(type)}.`;

export const hasProblem = (type: string) => `has() looks for a name in a row or a map, but this is ${human(type)}.`;

// When the value comes from a row, what it is shows only as the expression runs, and
// there Google's engine doesn't say what it found.
export const HAS_NEITHER = "has() looks for a name in a row or a map, but this is neither.";

export const rangeProblem = (type: string) =>
  `exists(), all(), exists_one(), filter() and map() go after a list, but this is ${human(type)}.`;

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

// Names the engines read as types (int on its own is the type, not a value): none is
// a name a template has.
const TYPE_WORDS = new Set([
  "bool", "bytes", "double", "duration", "dyn", "google", "int", "list", "map", "null_type", "optional_type", "string",
  "timestamp", "type", "uint",
]);
const FORMS = forms();
// The list functions, with a rule to show how each is written.
const LIST_FUNCTIONS: Record<string, string> = {
  exists: "r.attempts > 0", all: "r.attempts > 0", exists_one: "r.attempts > 0", filter: "r.attempts > 0", map: "r.ip",
};
const HAS = "has() takes one name with a dot in it, such as has(item.ip) or has(answers.title).";

const values = (count: number) => (count === 0 ? "nothing" : count === 1 ? "1 value" : `${count} values`);

/** What's wrong with how a function is called, before any types are looked at. */
export function callProblem(call: Call, tokens: Token[], shape: Shape): string | null {
  const name = call.name;
  if (name === "has") {
    const fits = !call.member && call.args.length === 1 && shape.selects.has(call.args[0].join(":"));
    return fits ? null : HAS;
  }
  if (Object.hasOwn(LIST_FUNCTIONS, name)) {
    let named = false;
    if (call.args.length === 2 && call.args[0][1] - call.args[0][0] === 1) {
      const first = tokens[call.args[0][0]];
      named = first.kind === "ident" && !RESERVED.has(first.text) && !["true", "false", "null", "in"].includes(first.text);
    }
    if (call.member && named) return null;
    return `${name}() goes after a list, with a name for each item and then a rule: answers.rows.${name}(r, ${LIST_FUNCTIONS[name]}).`;
  }
  const counts = FORMS.get(`${name}:${call.member}`);
  if (counts === undefined) {
    return call.member
      ? `${name}() is written on its own, with its values inside the brackets: ${name}(...).`
      : `${name}() is written after the value it works on: value.${name}(...).`;
  }
  if (counts.has(call.args.length)) return null;
  const allowed = [...counts].sort((a, b) => a - b);
  const last = values(allowed[allowed.length - 1]);
  const takes = allowed.length === 1 ? last : `${allowed.slice(0, -1).join(", ")} or ${last}`;
  return `${name}() takes ${takes} inside its brackets, not ${call.args.length || "none"}.`;
}

const KEY_KINDS: Record<string, string> = { text: "text", number: "a whole number", bool: "yes or no" };

/** A map key that's written out (text, a whole number, true or false), as its value. */
function keyOf(tokens: Token[], start: number, end: number): string | null {
  const negative = end - start === 2 && tokens[start].kind === "punct" && tokens[start].text === "-";
  if (end - start !== 1 && !negative) return null;
  const token = tokens[end - 1];
  if (token.kind === "string" && !negative) return `text:${unquote(token.text)}`;
  if (token.kind === "number" && /^(?:[0-9]+|0x[0-9a-fA-F]+)$/.test(token.text)) return `number:${negative ? -BigInt(token.text) : BigInt(token.text)}`;
  if (token.kind === "ident" && (token.text === "true" || token.text === "false") && !negative) return `bool:${token.text}`;
  return null;
}

/**
 * What Skjald refuses from the words alone, the same on both sides: functions outside
 * the list, matches(), unknown names and a whole group of names as a value. An
 * expression can pass this half-written; whether it reads is inspect()'s to say.
 */
export function validate(expr: string, declared: ReadonlySet<string>): Token[] {
  // Counted in characters, as the server counts: an emoji is one, not two.
  if (expr.length > MAX_LENGTH && characters(expr) > MAX_LENGTH) {
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

/**
 * Skjald's own checks, the same on both sides; the engine's type check follows. After
 * validate(), the syntax is read (reader.ts) and every call and map held to how it may
 * be written. Gives the expression's tokens and its shape.
 */
export function inspect(expr: string, declared: ReadonlySet<string>): { tokens: Token[]; shape: Shape } {
  const tokens = validate(expr, declared);
  for (const path of paths(tokens)) {
    if (TYPE_WORDS.has(path.names[0]) && declaredPrefix(path, declared) === null) {
      throw new ExpressionError("compile", unknownName(path.names.join(".")));
    }
  }
  let shape: Shape;
  try {
    shape = read(expr, tokens);
  } catch (error) {
    if (error instanceof Unreadable) throw new ExpressionError(error.kind, error.message);
    throw error;
  }
  for (const call of shape.calls) {
    const problem = callProblem(call, tokens, shape);
    if (problem !== null) throw new ExpressionError("compile", problem);
  }
  for (const keys of shape.maps) {
    // Keys written out are looked at now: one that's there twice makes the map fail on
    // the server and count once in the browser, and one of another kind than the rest
    // can never be found by what the others are found by.
    const seen = new Set<string>();
    let first: string | null = null;
    for (const [start, end] of keys) {
      const key = keyOf(tokens, start, end);
      if (key === null) continue;
      const kind = key.split(":")[0];
      first ??= kind;
      if (kind !== first) {
        throw new ExpressionError("compile", `A map's keys must all be the same kind, and this one has ${KEY_KINDS[first]} and ${KEY_KINDS[kind]}.`);
      }
      if (seen.has(key)) {
        const written = expr.slice(tokens[start].start, tokens[end - 1].end);
        throw new ExpressionError("compile", `A map has the key ${written} twice: each key can be there once.`);
      }
      seen.add(key);
    }
  }
  return { tokens, shape };
}

/** cel-js's names for types as Skjald writes them: a value read from a row is dyn<int>. */
const plainType = (type: string) => type.replace(/^dyn<(.+)>$/, "$1");

/**
 * What cel-js reports, in Skjald's words where it's a common error. asked: the
 * expression asks has() and has no "in" of its own, so an "in" cel-js complains of is
 * the one has() was written out as.
 */
function engineMessage(error: unknown, asked = false, running = false): string {
  const raw = error instanceof Error ? error.message : String(error);
  const first = raw.split("\n")[0];
  let match = /^Unknown variable: (\S+)/.exec(first);
  if (match) return unknownName(unaliased(match[1]));
  if (first.startsWith("Logical operator requires bool operands")) return LOGICAL;
  match = /^Ternary branches must have the same type, got '(.+)' and '(.+)'$/.exec(first);
  if (match) return branches(match[1], match[2]);
  match = /^Ternary condition must be bool, got '(.+)'$/.exec(first);
  if (match) return conditionProblem(plainType(match[1]));
  if (first.startsWith("List index must be int")) return LIST_PICK;
  match = /^(\w+)\(var, predicate\) predicate must return bool, got '(.+)'$/.exec(first);
  if (match) return ruleProblem(match[1], plainType(match[2]));
  match = /^Expression of type '(.+)' cannot be range of a comprehension/.exec(first);
  if (match) return rangeProblem(plainType(match[1]));
  match = /^Cannot index type '([^']+)'/.exec(first);
  if (match) return pickProblem(plainType(match[1]));
  match = /^no such overload: (.+?) (==|!=|<=|>=|<|>|\+|-|\*|\/|%|in) (.+)$/.exec(first);
  if (match && match[2] === "in" && asked) return running ? HAS_NEITHER : hasProblem(plainType(match[3]));
  if (match) return operatorProblem(match[2], [plainType(match[1]), plainType(match[3])]);
  match = /^no such overload: ([!-])(.+)$/.exec(first);
  if (match) return operatorProblem(match[1], [plainType(match[2])]);
  match = /^found no matching overload for '(?:(.+)\.)?([A-Za-z_]\w*)\((.*)\)'$/.exec(first);
  if (match) return functionProblem(match[2], [...(match[1] ? [match[1]] : []), ...splitTypes(match[3])].map(plainType));
  if (first.startsWith("Exceeded maxDepth")) return TOO_DEEP;
  return first;
}

interface Node {
  op: string;
  args: unknown;
  checkedType?: { name: string };
}

/** A checked node's type as Skjald writes it; dyn when cel-js didn't settle on one. */
function typeOf(node: Node | undefined): string {
  const name = node?.checkedType?.name ?? "dyn";
  return name
    .replaceAll("google.protobuf.Timestamp", "timestamp")
    .replaceAll("google.protobuf.Duration", "duration")
    .replace(/\b[A-Z]\b/g, "dyn");
}

function typeParts(type: string): string[] {
  const inner = type.slice(type.indexOf("<") + 1, -1);
  return type.includes("<") ? splitTypes(inner) : [];
}

/** Whether a value of one type can go where the shared list asks for another. */
function fitsType(given: string, wanted: string): boolean {
  if (given === "dyn" || wanted === "dyn" || given === wanted) return true;
  const kind = given.split("<")[0];
  if (kind !== wanted.split("<")[0] || (kind !== "list" && kind !== "map")) return false;
  const [have, want] = [typeParts(given), typeParts(wanted)];
  return want.every((part, i) => fitsType(have[i] ?? "dyn", part));
}

// Each function's overloads as the types they take, what it's written after first.
const OVERLOADS = new Map<string, string[][]>();
for (const f of FUNCTIONS) {
  if (f.name === "has" || Object.hasOwn(LIST_FUNCTIONS, f.name)) continue;
  for (const { signature } of f.overloads) {
    const match = /^(?:(.+)\.)?(\w+)\((.*)\):/.exec(signature);
    if (!match) continue;
    const key = `${f.name}:${match[1] !== undefined}`;
    OVERLOADS.set(key, [...(OVERLOADS.get(key) ?? []), [...(match[1] ? [match[1]] : []), ...splitTypes(match[3])].map((t) => t.replaceAll(" ", ""))]);
  }
}

/**
 * What cel-js takes and Google's checker doesn't, found in the checked tree: a function
 * given a kind of value the shared list doesn't have it take (cel-js only looks once
 * the expression runs, when it's called on a value from a row), a map asked for a key
 * of another kind than its own, and a name read from a date.
 */
function heldProblem(node: unknown): string | null {
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = heldProblem(child);
      if (found) return found;
    }
    return null;
  }
  if (!node || typeof node !== "object" || !("op" in node)) return null;
  const { op, args } = node as Node;
  if ((op === "call" || op === "rcall") && Array.isArray(args)) {
    const name = unaliased(String(args[0]));
    const operands = (op === "rcall" ? [args[1], ...(args[2] as Node[])] : (args[1] as Node[])) as Node[];
    const overloads = OVERLOADS.get(`${name}:${op === "rcall"}`);
    if (overloads) {
      const types = operands.map(typeOf);
      const spaced = (type: string) => type.replaceAll(" ", "");
      if (!overloads.some((o) => o.length === types.length && o.every((wanted, i) => fitsType(spaced(types[i]), wanted)))) {
        return functionProblem(name, types);
      }
    }
  }
  if (op === "[]" && Array.isArray(args)) {
    const [container, key] = (args as Node[]).map(typeOf);
    const [wanted] = typeParts(container);
    if (container.startsWith("map<") && !fitsType(key, wanted)) return keyProblem(wanted, key);
  }
  if (op === "." && Array.isArray(args)) {
    // cel-js would look for a name in a date when the expression runs.
    const from = typeOf(args[0] as Node);
    if (from === "timestamp" || from === "duration") return pickProblem(from);
  }
  return heldProblem(args);
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
/** A length of time as plain data (cel-js's own doesn't survive the trip from the worker). */
export interface Span {
  "@duration": number;
}

/** Whether a plain value is a length of time, in seconds. */
export function isSpan(value: unknown): value is Span {
  return !!value && typeof value === "object" && typeof (value as Span)["@duration"] === "number" && Object.keys(value).length === 1;
}

type CelDuration = { seconds: bigint | number; nanos: number; addDuration: unknown };
const isCelDuration = (value: unknown): value is CelDuration =>
  !!value && typeof value === "object" && typeof (value as CelDuration).addDuration === "function" && "nanos" in value;

export function plain(value: unknown): unknown {
  if (typeof value === "bigint") return Number(value);
  if (isCelDuration(value)) return { "@duration": Number(value.seconds) + value.nanos / 1e9 } satisfies Span;
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

// What makes each kind of value empty: has(answers.title) is whether the answer is
// anything else, written out for the engine as a comparison.
const FILLED: Record<string, string> = {
  string: ' != ""',
  int: " != 0",
  double: " != 0.0",
  bool: " != false",
  timestamp: ' != timestamp("1970-01-01T00:00:00Z")',
  duration: ' != duration("0s")',
  list: ".size() != 0",
  map: ".size() != 0",
};

/** Checks and evaluates expressions over one set of declared names. */
export class Engine {
  readonly declarations: Map<string, TypeSpec>;
  readonly #declared: Set<string>;
  readonly #env: Environment;
  readonly #zone: string;
  readonly #language: string;

  constructor(declarations: Record<string, string>, options: EngineOptions = {}) {
    this.declarations = new Map(Object.entries(declarations).map(([name, text]) => [name, parseType(text)]));
    this.#declared = new Set(this.declarations.keys());
    this.#zone = options.timezone ?? DEFAULT_ZONE;
    this.#language = options.language ?? "en";
    const locale = LOCALES[this.#language];
    if (!locale) throw new Error(`No locale for '${options.language}'.`);
    const impls = implementations({ zone: this.#zone, locale, tables: options.tables ?? {} });
    let env = new Environment({ homogeneousAggregateLiterals: false });
    for (const overload of browserOverloads()) {
      env = env.registerFunction(celJsType(aliased(overload.signature)), impls[overload.id] as (...args: unknown[]) => unknown);
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

  /** Text written out where a pattern or a date goes is checked now, not each time the expression runs. */
  #literals(tokens: Token[], shape: Shape) {
    const written = (call: Call, index: number): string | null => {
      if (index >= call.args.length || call.args[index][1] - call.args[index][0] !== 1) return null;
      const token = tokens[call.args[index][0]];
      return token.kind === "string" ? unquote(token.text) : null;
    };
    for (const call of shape.calls) {
      if (call.member) continue;
      try {
        if (call.name === "re_match" || call.name === "re_replace") {
          const pattern = written(call, 1);
          if (pattern === null) continue;
          const compiled = regex(pattern);
          const replacement = call.name === "re_replace" ? written(call, 2) : null;
          if (replacement !== null) replacementParts(replacement, compiled.groupCount(), compiled.namedGroups());
        } else if (call.name === "date") {
          const text = written(call, 0);
          if (text !== null) dateFrom(text, this.#zone);
        } else if (call.name === "format_date") {
          const pattern = written(call, 1);
          if (pattern !== null) formatDate(EPOCH, pattern, this.#zone, LOCALES[this.#language]);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        throw new ExpressionError("compile", message.replace("The pattern isn't", `The pattern in ${call.name}() isn't`));
      }
    }
  }

  /**
   * The expression as cel-js gets it: has() of a declared name as whether it's filled
   * in, has() of anything else as whether the name is in the row (the one way of
   * asking that both engines answer alike), Skjald's own functions by their names, and
   * a decimal that starts with its point with a 0 before it, which cel-js needs.
   */
  #rewritten(expr: string, tokens: Token[], shape: Shape): string {
    const edits = new Map<number, string>();
    for (const call of shape.calls) {
      if (call.name === "has") {
        const [start, end] = call.args[0];
        const names = tokens.slice(start, end);
        const plain = names.every((t, i) => (i % 2 === 0 ? t.kind === "ident" : t.text === "."));
        const spec = plain ? this.declarations.get(names.map((t) => t.text).join("")) : undefined;
        edits.set(call.at, "");
        if (spec) {
          edits.set(end, `${FILLED[spec.name] ?? " != null"})`);
        } else {
          edits.set(call.at + 1, `("${tokens[end - 1].text}" in (`);
          edits.set(end - 2, ")");
          edits.set(end - 1, "");
        }
      } else if (ALIASED.has(call.name)) {
        edits.set(call.at, ALIAS + call.name);
      }
    }
    tokens.forEach((token, index) => {
      if (token.kind === "number" && token.text.startsWith(".")) edits.set(index, `0${token.text}`);
    });
    if (!edits.size) return expr;
    let out = "";
    let last = 0;
    tokens.forEach((token, index) => {
      out += expr.slice(last, token.start) + (edits.get(index) ?? token.text);
      last = token.end;
    });
    return out + expr.slice(last);
  }

  #compile(expr: string) {
    const { tokens, shape } = inspect(expr, this.#declared);
    this.#literals(tokens, shape);
    const asked = shape.calls.some((call) => call.name === "has") && !tokens.some((t) => t.kind === "ident" && t.text === "in");
    let parsed;
    try {
      parsed = this.#env.parse(this.#rewritten(expr, tokens, shape));
    } catch (error) {
      throw new ExpressionError("compile", engineMessage(error, asked));
    }
    const checked = parsed.check();
    if (!checked.valid) throw new ExpressionError("compile", engineMessage(checked.error, asked));
    if (comparesMixedNumbers(parsed.ast)) throw new ExpressionError("compile", MIXED_COMPARISON);
    const held = heldProblem(parsed.ast);
    if (held !== null) throw new ExpressionError("compile", held);
    return { parsed, type: checked.type ?? "dyn", asked };
  }

  /** The type the expression gives, if Skjald will run it; else ExpressionError. */
  check(expr: string): string {
    // cel-js leaves a list or map of mixed or unknown items without a type inside.
    return this.#compile(expr)
      .type.replaceAll("google.protobuf.Timestamp", "timestamp")
      .replaceAll("google.protobuf.Duration", "duration")
      .replace(/\blist\b(?!<)/g, "list<dyn>")
      .replace(/\bmap\b(?!<)/g, "map<dyn, dyn>")
      .replace(/\b[A-Z]\b/g, "dyn");
  }

  /** The declared names the expression reads. */
  references(expr: string): string[] {
    return references(validate(expr, this.#declared), this.#declared);
  }

  /** The value as cel-js gives it: whole numbers as bigint. */
  evaluateRaw(expr: string, values: Record<string, unknown>): unknown {
    const { parsed, asked } = this.#compile(expr);
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
      throw new ExpressionError("runtime", engineMessage(error, asked, true));
    }
  }

  evaluate(expr: string, values: Record<string, unknown>): unknown {
    return plain(this.evaluateRaw(expr, values));
  }
}
