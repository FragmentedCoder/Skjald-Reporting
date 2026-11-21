// Reading an expression's shape from its tokens: Skjald's own check of the syntax, the
// browser's copy of backend/app/cel/reader.py with the same rules. Both engines parse
// CEL, but not quite the same CEL: Google's takes a name that starts with a dot and
// stops at 32 steps deep, cel-js takes an IF inside an IF without brackets and whole
// numbers too large to hold, and each words a syntax error its own way. So the
// expression is read here first: what neither or only one engine would take is refused
// in Skjald's words, and what's read is the same for both.
//
// What comes back is the expression's shape: every call with where its arguments are,
// every map with where its keys are. How deep it goes is counted the way Google's
// parser counts, which is what limits it.

import { characters, type Token } from "./lexer";

/** Words CEL keeps for itself: none can be a name. */
export const RESERVED = new Set([
  "as", "break", "const", "continue", "else", "for", "function", "if", "import", "let", "loop", "package",
  "namespace", "return", "var", "void", "while",
]);
const LITERALS = ["true", "false", "null"];
const RELATIONS = ["<", "<=", ">", ">=", "==", "!="];
const INT = /^(?:[0-9]+|0x[0-9a-fA-F]+)$/;
const FLOAT = /^(?:(?:[0-9]+\.[0-9]+|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[0-9]+[eE][+-]?[0-9]+)$/;
const ESCAPES: Record<string, string> = {
  a: "\x07", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t", v: "\v", "\\": "\\", "?": "?", '"': '"', "'": "'", "`": "`",
};
// How many hex digits follow \x, \u and \U.
const WIDTHS = new Map([["x", 2], ["X", 2], ["u", 4], ["U", 8]]);
const HEX = /^[0-9a-fA-F]+$/;
const MAX_INT = 2n ** 63n - 1n;

// Google's parser follows an expression 32 steps deep and takes 33 expressions inside
// each other; cel-js would go further, so the limit is said here for both.
const MAX_DEPTH = 32;
const MAX_NESTING = 33;

const END = "The expression stops before it's finished.";
export const TOO_DEEP =
  "This expression has too many steps in a row or inside each other: split it into calculated values, or add many numbers up with sum([...]).";

/** An expression Skjald won't read; the message is fit to show. */
export class Unreadable extends Error {
  constructor(
    readonly kind: "invalid" | "compile",
    message: string,
  ) {
    super(message);
  }
}

export interface Call {
  name: string;
  /** Written after a value and a dot, as in answers.title.size(). */
  member: boolean;
  /** Where the name is among the tokens, and where each argument starts and ends. */
  at: number;
  args: [number, number][];
}

export interface Shape {
  calls: Call[];
  /** Each map's keys: where each starts and ends among the tokens. */
  maps: [number, number][][];
  /** Runs of tokens that are a value, a dot and a name, and nothing more ("start:end"). */
  selects: Set<string>;
}

/** The text a text literal stands for; null if it has an escape CEL doesn't know. */
export function unquote(text: string): string | null {
  const start = "rR".includes(text[0]) ? 1 : 0;
  const quote = text.startsWith(text[start].repeat(3), start) ? text[start].repeat(3) : text[start];
  const body = text.slice(start + quote.length, text.length - quote.length);
  if (start === 1) {
    // Google's engine won't have a raw text end in a backslash.
    return (body.length - body.replace(/\\+$/, "").length) % 2 ? null : body;
  }
  let out = "";
  let i = 0;
  while (i < body.length) {
    const c = body[i];
    if (c !== "\\") {
      out += c;
      i += 1;
      continue;
    }
    const code = body.slice(i + 1, i + 2);
    if (Object.hasOwn(ESCAPES, code)) {
      out += ESCAPES[code];
      i += 2;
      continue;
    }
    const width = WIDTHS.get(code);
    let digits: string;
    if (width !== undefined) {
      digits = body.slice(i + 2, i + 2 + width);
      i += 2 + width;
    } else if (code && "0123".includes(code)) {
      digits = body.slice(i + 1, i + 4);
      i += 4;
      if (!/^[0-3][0-7][0-7]$/.test(digits)) return null;
      out += String.fromCodePoint(parseInt(digits, 8));
      continue;
    } else {
      return null;
    }
    if (digits.length !== width || !HEX.test(digits)) return null;
    const value = parseInt(digits, 16);
    if (value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)) return null;
    out += String.fromCodePoint(value);
  }
  return out;
}

class Reader {
  i = 0;
  // How many expressions sit inside each other here: brackets, arguments, an ELSE.
  // Each expression gives back how deep it goes, counted as Google's parser counts:
  // one for each step that isn't a pair of brackets.
  level = 0;
  readonly calls: Call[] = [];
  readonly maps: [number, number][][] = [];
  readonly selects = new Set<string>();

  constructor(
    readonly expr: string,
    readonly tokens: Token[],
  ) {}

  /** A token's place, counted in characters from 1, as the server counts. */
  position(token: Token): number {
    return characters(this.expr.slice(0, token.start)) + 1;
  }

  punct(...texts: string[]): boolean {
    const token = this.tokens[this.i];
    return token !== undefined && token.kind === "punct" && texts.includes(token.text);
  }

  word(text: string): boolean {
    const token = this.tokens[this.i];
    return token !== undefined && token.kind === "ident" && token.text === text;
  }

  unexpected(): Unreadable {
    const token = this.tokens[this.i];
    if (token === undefined) return new Unreadable("compile", END);
    const shown = [...token.text];
    const text = shown.length <= 20 ? token.text : shown.slice(0, 20).join("") + "…";
    return new Unreadable("compile", `Unexpected '${text}' at position ${this.position(token)}.`);
  }

  expect(text: string) {
    if (!this.punct(text)) throw this.unexpected();
    this.i += 1;
  }

  expression(): number {
    this.level += 1;
    if (this.level > MAX_NESTING) throw new Unreadable("invalid", TOO_DEEP);
    const condition = this.either();
    let height = condition;
    if (this.punct("?")) {
      this.i += 1;
      const first = this.either();
      if (this.punct("?")) {
        throw new Unreadable(
          "compile",
          `An IF inside the first result of another IF needs brackets around it (position ${this.position(this.tokens[this.i])}).`,
        );
      }
      this.expect(":");
      height = 1 + Math.max(condition, first, this.expression());
    }
    this.level -= 1;
    return height;
  }

  either(): number {
    const heights = [this.both()];
    while (this.punct("||")) {
      this.i += 1;
      heights.push(this.both());
    }
    return heights.length === 1 ? heights[0] : 1 + Math.max(...heights);
  }

  both(): number {
    const heights = [this.relation()];
    while (this.punct("&&")) {
      this.i += 1;
      heights.push(this.relation());
    }
    return heights.length === 1 ? heights[0] : 1 + Math.max(...heights);
  }

  relation(): number {
    let height = this.sum();
    while (this.punct(...RELATIONS) || this.word("in")) {
      this.i += 1;
      height = 1 + Math.max(height, this.sum());
    }
    return height;
  }

  sum(): number {
    let height = this.product();
    while (this.punct("+", "-")) {
      this.i += 1;
      height = 1 + Math.max(height, this.product());
    }
    return height;
  }

  product(): number {
    let height = this.unary();
    while (this.punct("*", "/", "%")) {
      this.i += 1;
      height = 1 + Math.max(height, this.unary());
    }
    return height;
  }

  numberFollows(): boolean {
    return this.tokens[this.i + 1]?.kind === "number";
  }

  unary(): number {
    if (this.punct("!")) {
      while (this.punct("!")) this.i += 1;
      return 1 + this.member();
    }
    if (this.punct("-") && !this.numberFollows()) {
      while (this.punct("-")) this.i += 1;
      return 1 + this.member();
    }
    return this.member();
  }

  member(): number {
    const start = this.i;
    let height = this.primary();
    for (;;) {
      if (this.punct(".")) {
        this.i += 1;
        const name = this.tokens[this.i];
        if (name === undefined || name.kind !== "ident" || LITERALS.includes(name.text) || name.text === "in") {
          throw this.unexpected();
        }
        this.i += 1;
        if (this.punct("(")) {
          height = 1 + Math.max(height, ...this.args(name.text, true, this.i - 1));
        } else {
          height += 1;
          this.selects.add(`${start}:${this.i}`);
        }
      } else if (this.punct("[")) {
        this.i += 1;
        height = 1 + Math.max(height, this.expression());
        this.expect("]");
      } else {
        return height;
      }
    }
  }

  args(name: string, member: boolean, at: number): number[] {
    this.expect("(");
    const heights: number[] = [];
    const ranges: [number, number][] = [];
    if (!this.punct(")")) {
      for (;;) {
        const start = this.i;
        heights.push(this.expression());
        ranges.push([start, this.i]);
        if (!this.punct(",")) break;
        this.i += 1;
      }
    }
    this.expect(")");
    this.calls.push({ name, member, at, args: ranges });
    return heights;
  }

  primary(): number {
    const token = this.tokens[this.i];
    if (token === undefined) throw this.unexpected();
    if (token.kind === "number" || (this.punct("-") && this.numberFollows())) {
      const negative = token.kind !== "number";
      this.i += negative ? 1 : 0;
      this.number(this.tokens[this.i], negative);
      this.i += 1;
      return 1;
    }
    if (token.kind === "string") {
      this.text(token);
      this.i += 1;
      return 1;
    }
    if (token.kind === "punct") {
      if (token.text === "(") {
        this.i += 1;
        const height = this.expression();
        this.expect(")");
        return height;
      }
      if (token.text === "[") {
        this.i += 1;
        const heights = [0];
        while (!this.punct("]")) {
          heights.push(this.expression());
          if (!this.punct(",")) break;
          this.i += 1;
        }
        this.expect("]");
        return 1 + Math.max(...heights);
      }
      if (token.text === "{") {
        this.i += 1;
        const heights = [0];
        const keys: [number, number][] = [];
        while (!this.punct("}")) {
          const start = this.i;
          heights.push(this.expression());
          keys.push([start, this.i]);
          this.expect(":");
          heights.push(this.expression());
          if (!this.punct(",")) break;
          this.i += 1;
        }
        this.expect("}");
        this.maps.push(keys);
        return 1 + Math.max(...heights);
      }
      if (token.text === ".") {
        throw new Unreadable("invalid", `A name can't start with a dot (position ${this.position(token)}).`);
      }
      throw this.unexpected();
    }
    if (LITERALS.includes(token.text)) {
      this.i += 1;
      return 1;
    }
    if (token.text === "in") throw this.unexpected();
    this.i += 1;
    if (this.punct("(")) return 1 + Math.max(0, ...this.args(token.text, false, this.i - 1));
    if (RESERVED.has(token.text)) throw new Unreadable("compile", `${token.text} is a reserved word in expressions.`);
    return 1;
  }

  number(token: Token, negative: boolean) {
    const text = token.text;
    if ("uU".includes(text[text.length - 1]) && INT.test(text.slice(0, -1))) {
      throw new Unreadable("invalid", `Whole numbers are written without a u: ${text.slice(0, -1)} rather than ${text}.`);
    }
    if (INT.test(text)) {
      if (BigInt(text) > MAX_INT + (negative ? 1n : 0n)) throw new Unreadable("compile", `${text} is too large for a whole number.`);
    } else if (!FLOAT.test(text)) {
      throw new Unreadable("compile", `${text} isn't a number Skjald can read (position ${this.position(token)}).`);
    } else if (Number(text) === Infinity) {
      throw new Unreadable("compile", `${text} is too large for a number.`);
    }
  }

  text(token: Token) {
    const prefix = /^[rRbB]*/.exec(token.text)?.[0] ?? "";
    if (prefix.toLowerCase().includes("b")) {
      throw new Unreadable("invalid", `Text is written without a b before the quote (position ${this.position(token)}).`);
    }
    if (unquote(token.text) === null) {
      throw new Unreadable(
        "compile",
        `The text at position ${this.position(token)} has a backslash Skjald can't read: write \\\\ for a backslash itself.`,
      );
    }
  }
}

/** The expression's shape, if it's one both engines read the same way. */
export function read(expr: string, tokens: Token[]): Shape {
  const reader = new Reader(expr, tokens);
  const depth = reader.expression();
  if (reader.i < tokens.length) throw reader.unexpected();
  if (depth > MAX_DEPTH) throw new Unreadable("invalid", TOO_DEEP);
  return { calls: reader.calls, maps: reader.maps, selects: reader.selects };
}
