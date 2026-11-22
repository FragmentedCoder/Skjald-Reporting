// A report's answers between the browser and the server: what counts as an answer,
// which ones changed here and may be sent, and how the server's are taken in without
// losing what's being typed. Plain functions over plain data; the editor
// (editor.svelte.ts) holds the state and does the talking.
//
// The answers are kept by question ID, as the server keeps them: a question that isn't
// answered has no entry, and one cleared on purpose that would otherwise start as
// something (its "Starts as" rule) holds null, so it stays empty.

import type { Id, Question, Step } from "#lib/templates/types.js";
import { holds, type Checkout } from "./api";

export type Answers = Record<Id, unknown>;

/**
 * Whether a value is no answer, as the server reads it (backend/app/reports/answers.py):
 * nothing, a CVSS answer with no vector, a signature whose name isn't typed or isn't
 * confirmed.
 */
export function blank(question: Pick<Question, "type">, value: unknown): boolean {
  if (value === null || value === undefined || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value !== "object") return false;
  const parts = value as Record<string, unknown>;
  if (Object.keys(parts).length === 0) return true;
  if (question.type === "cvss") return !String(parts.vector ?? "").trim();
  if (question.type === "signature") return parts.confirmed !== true || !String(parts.name ?? "").trim();
  return false;
}

/**
 * What the answers hold once the technician has set a value: the value, or nothing
 * (undefined) when it's emptied; null when the question has a "Starts as" rule, so
 * that it stays empty instead of starting again.
 */
export function held(question: Pick<Question, "type" | "default">, value: unknown): unknown {
  if (!blank(question, value)) return value;
  return question.default?.trim() ? null : undefined;
}

/**
 * Whether two answers are the same, however their parts are ordered. Inside an answer,
 * a part that's null is the same as one that isn't there (a row's empty cell).
 */
export function same(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((item, i) => part(item, b[i]));
  }
  const [x, y] = [a as Record<string, unknown>, b as Record<string, unknown>];
  return [...new Set([...Object.keys(x), ...Object.keys(y)])].every((key) => part(x[key], y[key]));
}

const part = (a: unknown, b: unknown) => ((a ?? null) === null && (b ?? null) === null) || same(a, b);

/** Whether a question's answer here differs from the one the server keeps. */
export function differs(id: Id, here: Answers, kept: Answers): boolean {
  const [mine, theirs] = [here[id], kept[id]];
  // Not answered (undefined) isn't the same as cleared on purpose (null).
  if (mine === undefined || theirs === undefined || mine === null || theirs === null) return mine !== theirs;
  return !same(mine, theirs);
}

/**
 * An answer as it's sent: an empty one as null, and a picked person by ID alone (the
 * server looks their details up itself). A secret is sent as it was typed.
 */
export function toSend(question: Pick<Question, "type">, value: unknown): unknown {
  if (blank(question, value)) return null;
  if (question.type === "person") return { id: (value as { id?: unknown }).id };
  return value;
}

/** The questions whose answers changed here and aren't saved yet, in the form's order, each with its step. */
export function unsaved(form: Step[], here: Answers, kept: Answers): { step: Id; question: Question }[] {
  return form.flatMap((step) => step.questions.filter((q) => differs(q.id, here, kept)).map((question) => ({ step: step.id, question })));
}

/**
 * What a save sends: only the answers that changed, and only those in steps this
 * person holds (the server refuses a save that reaches outside them).
 */
export function toSave(form: Step[], checkouts: Checkout[], here: Answers, kept: Answers): Answers {
  const sent: Answers = {};
  for (const { step, question } of unsaved(form, here, kept)) {
    if (holds(checkouts, step)) sent[question.id] = toSend(question, here[question.id]);
  }
  return sent;
}

/**
 * The answers after the report is fetched again: the server's, with other people's
 * work in them, except where this browser has changes it hasn't saved yet. An answer
 * that's the same on both sides stays the one held here, so a field being read or
 * typed in isn't disturbed.
 */
export function merged(form: Step[], here: Answers, kept: Answers, fetched: Answers): Answers {
  const next: Answers = {};
  for (const question of form.flatMap((step) => step.questions)) {
    const id = question.id;
    const from = differs(id, here, kept) ? here : fetched;
    if (from[id] === undefined) continue;
    next[id] = here[id] !== undefined && !differs(id, here, fetched) ? here[id] : from[id];
  }
  return next;
}
