// Date helpers for template expressions, in the company's time zone: the browser's
// copy of backend/app/cel/dates.py. The shared cases hold both to the same answers,
// summer time included. A local time that happens twice (when summer time ends) means
// the first; one that never happens (when it starts) is read with the offset from
// before the change, so it lands an hour later, as Python's zoneinfo does.

export interface Locale {
  months: string[];
  short_months: string[];
  weekdays: string[];
  decimal: string;
  group: string;
}

interface Wall {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

const DAY_MS = 86_400_000;
const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(zone: string): Intl.DateTimeFormat {
  let found = formatters.get(zone);
  if (!found) {
    found = new Intl.DateTimeFormat("en-GB", {
      timeZone: zone,
      hourCycle: "h23",
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
      second: "numeric",
    });
    formatters.set(zone, found);
  }
  return found;
}

/** The wall clock in the zone at an instant. */
export function wallAt(ms: number, zone: string): Wall {
  const parts: Record<string, number> = {};
  for (const part of formatter(zone).formatToParts(new Date(ms))) {
    if (part.type !== "literal") parts[part.type] = Number(part.value);
  }
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    hour: parts.hour,
    minute: parts.minute,
    second: parts.second,
  };
}

const asUtc = (w: Wall) => Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute, w.second);
const offsetAt = (ms: number, zone: string) => asUtc(wallAt(ms, zone)) - Math.floor(ms / 1000) * 1000;

/** The instant a wall-clock time in the zone stands for. */
export function instantOf(wall: Wall, zone: string): number {
  const local = asUtc(wall);
  const before = offsetAt(local - DAY_MS, zone);
  const after = offsetAt(local + DAY_MS, zone);
  const early = local - before;
  const late = local - after;
  const valid = (ms: number) => asUtc(wallAt(ms, zone)) === local;
  // Twice (both valid) or never (neither): the offset from before the change.
  return !valid(early) && valid(late) ? late : early;
}

const DATE = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?(Z|[+-]\d{2}:\d{2})?$/;

export function parseDate(text: string, zone: string): Date {
  const match = DATE.exec(text);
  const invalid = new Error(`'${text}' isn't a date such as 2026-10-21 or 2026-10-21T14:30.`);
  if (!match) throw invalid;
  const [, year, month, day, hour, minute, second, offset] = match;
  const wall: Wall = {
    year: Number(year),
    month: Number(month),
    day: Number(day),
    hour: Number(hour ?? 0),
    minute: Number(minute ?? 0),
    second: Number(second ?? 0),
  };
  const check = new Date(asUtc(wall));
  if (
    check.getUTCFullYear() !== wall.year ||
    check.getUTCMonth() !== wall.month - 1 ||
    check.getUTCDate() !== wall.day ||
    wall.hour > 23 ||
    wall.minute > 59 ||
    wall.second > 59 ||
    wall.year < 1
  ) {
    throw invalid;
  }
  if (offset === undefined) return new Date(instantOf(wall, zone));
  if (offset === "Z") return new Date(asUtc(wall));
  const sign = offset[0] === "+" ? 1 : -1;
  const delta = (Number(offset.slice(1, 3)) * 60 + Number(offset.slice(4, 6))) * 60_000;
  return new Date(asUtc(wall) - sign * delta);
}

export function addDays(moment: Date, days: number, zone: string): Date {
  const wall = wallAt(moment.getTime(), zone);
  const moved = new Date(Date.UTC(wall.year, wall.month - 1, wall.day + days, wall.hour, wall.minute, wall.second));
  const target: Wall = {
    year: moved.getUTCFullYear(),
    month: moved.getUTCMonth() + 1,
    day: moved.getUTCDate(),
    hour: wall.hour,
    minute: wall.minute,
    second: wall.second,
  };
  // Keep the milliseconds the instant had.
  return new Date(instantOf(target, zone) + (moment.getTime() % 1000));
}

export function hoursBetween(start: Date, end: Date): number {
  return (end.getTime() - start.getTime()) / 3_600_000;
}

export function daysBetween(start: Date, end: Date, zone: string): number {
  const a = wallAt(start.getTime(), zone);
  const b = wallAt(end.getTime(), zone);
  return Math.round((Date.UTC(b.year, b.month - 1, b.day) - Date.UTC(a.year, a.month - 1, a.day)) / DAY_MS);
}

const TOKENS = new Set(["yyyy", "yy", "MMMM", "MMM", "MM", "M", "dd", "d", "EEEE", "HH", "H", "mm", "ss"]);
// Quoted text ('' is a quote mark), runs of one letter, anything else, or a stray quote.
const PATTERN = /'((?:[^']|'')*)'|([A-Za-z])\2*|[^A-Za-z']+|'/g;
const pad = (n: number, width = 2) => String(n).padStart(width, "0");

export function formatDate(moment: Date, pattern: string, zone: string, locale: Locale): string {
  const w = wallAt(moment.getTime(), zone);
  const weekday = (new Date(Date.UTC(w.year, w.month - 1, w.day)).getUTCDay() + 6) % 7;
  const values: Record<string, string> = {
    yyyy: pad(w.year, 4),
    yy: pad(w.year % 100),
    MMMM: locale.months[w.month - 1],
    MMM: locale.short_months[w.month - 1],
    MM: pad(w.month),
    M: String(w.month),
    dd: pad(w.day),
    d: String(w.day),
    EEEE: locale.weekdays[weekday],
    HH: pad(w.hour),
    H: String(w.hour),
    mm: pad(w.minute),
    ss: pad(w.second),
  };
  let out = "";
  for (const match of pattern.matchAll(PATTERN)) {
    const [text, quoted, letter] = match;
    if (quoted !== undefined) {
      out += quoted ? quoted.replaceAll("''", "'") : "'";
    } else if (letter !== undefined) {
      if (!TOKENS.has(text)) throw new Error(`${text} isn't part of a date pattern: put text in 'quotes'.`);
      out += values[text];
    } else if (text === "'") {
      throw new Error("A date pattern has a quote mark that isn't closed.");
    } else {
      out += text;
    }
  }
  return out;
}
