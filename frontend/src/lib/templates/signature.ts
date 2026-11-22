// A signature question's answer: a full name typed and a box ticked to confirm it, by
// someone who isn't a user of Skjald (the customer, a witness). Nobody draws a
// signature. Signed, the answer is kept as { name, confirmed: true, at }, where at is
// the moment the box was ticked (an ISO instant, UTC); not signed, it's absent or null.
// Anything else is read as not signed: an answer from the drawing pad this replaced
// holds strokes, and has no name to print.

/** The longest name the form takes. */
export const NAME_MAX = 200;

/** A signature question's answer as it's kept. */
export interface SignatureAnswer {
  name: string;
  confirmed: true;
  at: string;
}

/** A signature read: the name confirmed, and when. */
export interface Signed {
  name: string;
  at: Date;
}

// A moment with its offset written out, as Date.toISOString() and the server write one.
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

/** Who signed and when, or null when the answer isn't signed (or isn't a signature). */
export function signed(raw: unknown): Signed | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const { name, confirmed, at } = raw as Record<string, unknown>;
  if (typeof name !== "string" || confirmed !== true || typeof at !== "string" || !INSTANT.test(at)) return null;
  const typed = name.trim();
  const moment = new Date(at);
  return !typed || typed.length > NAME_MAX || Number.isNaN(moment.getTime()) ? null : { name: typed, at: moment };
}

/**
 * The answer for a name confirmed now, to the second; null when there's no name to
 * confirm (blank, or longer than the form takes), so nothing is signed.
 */
export function sign(name: string, now: Date = new Date()): SignatureAnswer | null {
  const typed = name.trim();
  if (!typed || typed.length > NAME_MAX) return null;
  return { name: typed, confirmed: true, at: now.toISOString().replace(/\.\d{3}Z$/, "Z") };
}
