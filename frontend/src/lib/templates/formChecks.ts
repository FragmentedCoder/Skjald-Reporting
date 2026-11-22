// What keeps one answer from being sent for review, as the form shows it: the answer's
// own check (answers.ts), how many are chosen, how many rows there are, and each row's
// cells. "Try it" lists these under "Check the answers", and each field shows its own.
// And what keeps a whole report from it: missingAnswers(), which the server works out
// too for a real report (backend/app/reports/form.py). shared/reports/form.json holds
// the two to the same list.

import { checkAnswer } from "./answers";
import { fieldType, settingsOf } from "./fields";
import type { PreviewModel } from "./preview";
import type { Id, Question, TemplateContent } from "./types";

type Column = { key: string; label: string; type: string; required?: boolean; settings?: Record<string, unknown> };

const blank = (value: unknown) => value === null || value === undefined || value === "";
const several = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`;

/** What's wrong with one cell of a row: its type's check, or that its column must be filled in. */
export function cellProblem(column: Column, value: unknown): string | null {
  if (blank(value)) return column.required ? "This is required." : null;
  return checkAnswer(column.type, settingsOf(column.type, column.settings ?? {}), value);
}

/** What's wrong with the answer, or null: the first problem, said so it can stand in a list. */
export function answerProblem(question: Pick<Question, "type" | "settings">, value: unknown): string | null {
  const s = settingsOf(question.type, question.settings);
  switch (question.type) {
    case "cvss":
      return checkAnswer("cvss", s, (value as { vector?: string } | null | undefined)?.vector ?? "");
    case "multi_select": {
      if (!Array.isArray(value)) return null;
      const [fewest, most] = [s.min_selected as number | null, s.max_selected as number | null];
      if (fewest !== null && fewest !== undefined && value.length < fewest) return `Choose at least ${fewest}.`;
      if (most !== null && most !== undefined && value.length > most) return `Choose at most ${most}.`;
      return null;
    }
    case "repeating":
    case "table": {
      const columns = (s.columns ?? []) as Column[];
      const rows = Array.isArray(value) ? (value as (Record<string, unknown> | null)[]) : [];
      const fixed = question.type === "table" ? ((s.rows ?? []) as { label: string }[]) : null;
      if (!fixed) {
        const fewest = Number(s.min_rows ?? 0);
        if (rows.length < fewest) return `Add at least ${several(fewest, "row")}.`;
        if (rows.length > Number(s.max_rows ?? 100)) return `Keep it to ${several(Number(s.max_rows ?? 100), "row")}.`;
      }
      // A table's rows are all there to fill in, written or not; a group's are the ones added.
      const count = fixed ? fixed.length : rows.length;
      for (let r = 0; r < count; r++) {
        for (const column of columns) {
          const problem = cellProblem(column, rows[r]?.[column.key]);
          if (problem) return `${fixed ? fixed[r].label || `Row ${r + 1}` : `Row ${r + 1}`}, ${column.label}: ${problem}`;
        }
      }
      return null;
    }
    default:
      return checkAnswer(question.type, s, value);
  }
}

/** One thing that keeps a report from going for review: where it is, and what to say. */
export interface Missing {
  step: Id;
  question: Id;
  /** The field's own words, or "is required." to follow the question's label. */
  message: string;
}

/**
 * Everything that would keep a report from going for review, in the form's order. Only
 * questions that are shown, on steps that are shown, and that ask something count; a
 * question not answered yet counts as what it starts as. Each says its own problem
 * (answerProblem), else what its rule says ("valid_when"), else that it's required and
 * empty.
 *
 * model: what the form works out for these answers (preview.ts); answers: by question
 * ID, as they're kept.
 */
export function missingAnswers(
  content: Pick<TemplateContent, "form">,
  model: Pick<PreviewModel, "formHidden" | "formRequired" | "invalid" | "defaults"> | null | undefined,
  answers: Record<Id, unknown>,
): Missing[] {
  const hidden = new Set(model?.formHidden ?? []);
  const required = new Set(model?.formRequired ?? []);
  const invalid = new Map((model?.invalid ?? []).map((i) => [i.id, i.message]));
  const found: Missing[] = [];
  for (const step of content.form) {
    if (hidden.has(step.id)) continue;
    for (const q of step.questions) {
      if (hidden.has(q.id) || !fieldType(q.type).asks || q.type === "calculated") continue;
      const kept = answers[q.id];
      const value = kept === undefined ? model?.defaults[q.id] : kept;
      const empty = value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length)
        || (q.type === "cvss" && !(value as { vector?: string } | null)?.vector);
      // What the field itself says: its own check, how many are chosen, the rows and their cells.
      const message = answerProblem(q, value) ?? invalid.get(q.id) ?? (required.has(q.id) && empty ? "is required." : null);
      if (message) found.push({ step: step.id, question: q.id, message });
    }
  }
  return found;
}
