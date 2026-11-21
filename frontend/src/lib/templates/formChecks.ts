// What keeps one answer from being sent for review, as the form shows it: the answer's
// own check (answers.ts), how many are chosen, how many rows there are, and each row's
// cells. "Try it" lists these under "Check the answers", and each field shows its own.

import { checkAnswer } from "./answers";
import { settingsOf } from "./fields";
import type { Question } from "./types";

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
