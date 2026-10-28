// A tokenizer for CEL, and what Skjald reads from the tokens: the browser's copy of
// backend/app/cel/lexer.py, with the same rules. The validator works on tokens rather
// than on either engine's syntax tree, so both sides refuse the same expressions with
// the same words. The tokens also say which declared names an expression reads, and
// where, so renaming a question can rewrite its expressions without touching text
// inside quotes.

export type Kind = "ident" | "number" | "string" | "punct";

export interface Token {
  kind: Kind;
  text: string;
  start: number;
  end: number;
}

export class LexError extends Error {}

const PUNCT2 = ["==", "!=", "<=", ">=", "&&", "||"];
const PUNCT1 = "<>+-*/%!?:.,[]{}()";
const isIdentStart = (c: string) => /^[_a-zA-Z]$/.test(c);
const isIdentPart = (c: string) => /^[_a-zA-Z0-9]$/.test(c);
const isDigit = (c: string) => c >= "0" && c <= "9";
const isHex = (c: string) => /^[0-9a-fA-F]$/.test(c);
const SPACE = " \t\n\r\f";

function prefixLength(expr: string, i: number): number {
  for (const length of [2, 1]) {
    const prefix = expr.slice(i, i + length).toLowerCase();
    const valid = length === 1 ? prefix === "r" || prefix === "b" : prefix === "rb" || prefix === "br";
    const quote = expr.slice(i + length, i + length + 1);
    if (valid && (quote === "'" || quote === '"')) return length;
  }
  return 0;
}

function startsString(expr: string, i: number): boolean {
  return expr[i] === "'" || expr[i] === '"' || prefixLength(expr, i) > 0;
}

function stringEnd(expr: string, i: number): number {
  const prefix = prefixLength(expr, i);
  const raw = expr.slice(i, i + prefix).toLowerCase().includes("r");
  let j = i + prefix;
  const quote = expr.startsWith(expr[j].repeat(3), j) ? expr[j].repeat(3) : expr[j];
  j += quote.length;
  while (j < expr.length) {
    if (!raw && expr[j] === "\\") {
      j += 2;
      continue;
    }
    if (expr.startsWith(quote, j)) return j + quote.length;
    if (quote.length === 1 && expr[j] === "\n") break;
    j += 1;
  }
  throw new LexError(`Text starting at position ${i + 1} has no closing quote.`);
}

function numberEnd(expr: string, i: number): number {
  const n = expr.length;
  if (expr.startsWith("0x", i) || expr.startsWith("0X", i)) {
    let j = i + 2;
    while (j < n && isHex(expr[j])) j += 1;
    return j < n && "uU".includes(expr[j]) ? j + 1 : j;
  }
  let j = i;
  while (j < n && isDigit(expr[j])) j += 1;
  let decimal = false;
  if (j < n && expr[j] === "." && j + 1 < n && isDigit(expr[j + 1])) {
    decimal = true;
    j += 1;
    while (j < n && isDigit(expr[j])) j += 1;
  }
  if (j < n && "eE".includes(expr[j])) {
    let k = j + 1;
    if (k < n && "+-".includes(expr[k])) k += 1;
    if (k < n && isDigit(expr[k])) {
      decimal = true;
      j = k;
      while (j < n && isDigit(expr[j])) j += 1;
    }
  }
  if (!decimal && j < n && "uU".includes(expr[j])) j += 1;
  return j;
}

export function tokenize(expr: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  const n = expr.length;
  while (i < n) {
    const c = expr[i];
    if (SPACE.includes(c)) {
      i += 1;
    } else if (expr.startsWith("//", i)) {
      const end = expr.indexOf("\n", i);
      i = end < 0 ? n : end;
    } else if (startsString(expr, i)) {
      const end = stringEnd(expr, i);
      tokens.push({ kind: "string", text: expr.slice(i, end), start: i, end });
      i = end;
    } else if (isIdentStart(c)) {
      let end = i + 1;
      while (end < n && isIdentPart(expr[end])) end += 1;
      tokens.push({ kind: "ident", text: expr.slice(i, end), start: i, end });
      i = end;
    } else if (isDigit(c) || (c === "." && i + 1 < n && isDigit(expr[i + 1]))) {
      const end = numberEnd(expr, i);
      tokens.push({ kind: "number", text: expr.slice(i, end), start: i, end });
      i = end;
    } else if (PUNCT2.includes(expr.slice(i, i + 2))) {
      tokens.push({ kind: "punct", text: expr.slice(i, i + 2), start: i, end: i + 2 });
      i += 2;
    } else if (PUNCT1.includes(c)) {
      tokens.push({ kind: "punct", text: c, start: i, end: i + 1 });
      i += 1;
    } else {
      throw new LexError(`Unexpected character '${c}' at position ${i + 1}.`);
    }
  }
  return tokens;
}

export interface Call {
  name: string;
  member: boolean;
  start: number;
}

/** Every function or macro called: a name followed by an opening bracket. */
export function calls(tokens: Token[]): Call[] {
  const found: Call[] = [];
  tokens.forEach((token, index) => {
    if (token.kind !== "ident" || index + 1 >= tokens.length) return;
    if (tokens[index + 1].text === "(") {
      found.push({ name: token.text, member: index > 0 && tokens[index - 1].text === ".", start: token.start });
    }
  });
  return found;
}

/** A run of names joined by dots, such as answers.cvss; never a function's name. */
export interface Path {
  names: string[];
  start: number;
  end: number;
}

export function paths(tokens: Token[]): Path[] {
  const found: Path[] = [];
  let index = 0;
  while (index < tokens.length) {
    const token = tokens[index];
    const afterDot = index > 0 && tokens[index - 1].text === ".";
    const isCall = index + 1 < tokens.length && tokens[index + 1].text === "(";
    if (token.kind !== "ident" || afterDot || isCall) {
      index += 1;
      continue;
    }
    const names = [token.text];
    let end = token.end;
    index += 1;
    while (
      index + 1 < tokens.length &&
      tokens[index].text === "." &&
      tokens[index + 1].kind === "ident" &&
      !(index + 2 < tokens.length && tokens[index + 2].text === "(")
    ) {
      names.push(tokens[index + 1].text);
      end = tokens[index + 1].end;
      index += 2;
    }
    found.push({ names, start: token.start, end });
  }
  return found;
}

/** The longest part of the path that is a declared name. */
export function declaredPrefix(path: Path, declared: ReadonlySet<string>): string | null {
  for (let length = path.names.length; length > 0; length--) {
    const candidate = path.names.slice(0, length).join(".");
    if (declared.has(candidate)) return candidate;
  }
  return null;
}

/** The declared names an expression reads, sorted. */
export function references(tokens: Token[], declared: ReadonlySet<string>): string[] {
  const found = new Set<string>();
  for (const path of paths(tokens)) {
    const name = declaredPrefix(path, declared);
    if (name !== null) found.add(name);
  }
  return [...found].sort();
}

/**
 * The expression with one name replaced by another wherever it's read, such as
 * answers.cvss becoming answers.cvss_score; text inside quotes stays as it is. Names
 * inside the old one move with it (answers.rows.ip when answers.rows is renamed).
 */
export function renameReference(expr: string, from: string, to: string): string {
  const wanted = from.split(".");
  let out = "";
  let last = 0;
  for (const path of paths(tokenize(expr))) {
    if (path.names.length < wanted.length) continue;
    if (!wanted.every((name, i) => path.names[i] === name)) continue;
    const tokens = tokenize(expr.slice(path.start, path.end));
    // The old name's last token ends where the replacement stops.
    const cut = tokens.filter((t) => t.kind === "ident")[wanted.length - 1].end;
    out += expr.slice(last, path.start) + to;
    last = path.start + cut;
  }
  return out + expr.slice(last);
}
