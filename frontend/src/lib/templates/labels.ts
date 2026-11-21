// What a name printed on its own shows for an answer picked from choices: the choice as
// the question shows it (its label), as an Answer block and a table print it. Rules
// compare the value a choice keeps ("hoej"), and anything worked out from an answer
// still prints as it's worked out; only a name standing alone in {{ }} prints the label:
// {{answers.status}}, several choices joined ({{answers.areas.join(", ")}}, the only way
// text prints a list), {{item.severity}} inside a section repeated for each row,
// {{answers.rows[0].severity}}, and a column of every row joined
// ({{answers.rows.map(row, row.severity).join(", ")}}), as the builder's lists offer them.
// Phase 3's renderer prints the same.

import { settingsOf } from "./fields";
import type { Question } from "./types";

export type LabelColumn = { key: string; type: string; settings?: Record<string, unknown> };

export interface LabelContext {
  /** The template's questions by variable name. */
  questions: Map<string, Pick<Question, "type" | "settings">>;
  /** An answer as expressions read it (plain values), by variable name: a list's rows, the choices made. */
  answer: (key: string) => unknown;
  /** Inside a section repeated for each row of a list: that list's columns. */
  item?: LabelColumn[];
}

const NAME = "[a-z][a-z0-9_]*";
const ANSWER = new RegExp(`^answers\\.(${NAME})$`);
const ITEM = new RegExp(`^item\\.(${NAME})$`);
const CELL = new RegExp(`^answers\\.(${NAME})\\[\\d+\\]\\.(${NAME})$`);
const STRING = '"((?:[^"\\\\]|\\\\.)*)"';
const JOINED = new RegExp(`^answers\\.(${NAME})\\.join\\(\\s*(?:${STRING})?\\s*\\)$`);
const EVERY = new RegExp(`^answers\\.(${NAME})\\.map\\(\\s*([a-z_][a-z0-9_]*)\\s*,\\s*\\2\\.(${NAME})\\s*\\)\\.join\\(\\s*"((?:[^"\\\\]|\\\\.)*)"\\s*\\)$`);

type Choice = { value: string; label: string };

/** One value as its question or column shows it: a choice's label, Yes and No as they've been named. */
function shown(type: string, settings: Record<string, unknown>, value: unknown): unknown {
  if (type === "dropdown" && typeof value === "string") {
    return ((settings.options ?? []) as Choice[]).find((o) => o.value === value)?.label ?? value;
  }
  if (type === "multi_select" && Array.isArray(value)) {
    const options = (settings.options ?? []) as Choice[];
    return value.map((v) => options.find((o) => o.value === v)?.label ?? v);
  }
  if (type === "yes_no" && typeof value === "boolean") {
    // Yes and No print in the report's language unless the question names them itself.
    const [yes, no] = [String(settings.yes_label ?? "Yes").trim(), String(settings.no_label ?? "No").trim()];
    if (yes === "Yes" && no === "No") return value;
    return value ? yes : no;
  }
  return value;
}

const columnsOf = (question: Pick<Question, "type" | "settings"> | undefined): LabelColumn[] =>
  question && (question.type === "repeating" || question.type === "table") ? ((settingsOf(question.type, question.settings).columns ?? []) as LabelColumn[]) : [];

const cell = (column: LabelColumn | undefined, value: unknown): unknown =>
  column ? shown(column.type, settingsOf(column.type, column.settings ?? {}), value) : value;

/** A list's columns, when a section is repeated for exactly its rows (answers.<list>). */
export function repeatedColumns(repeatFor: string | null | undefined, questions: LabelContext["questions"]): LabelColumn[] | undefined {
  const list = ANSWER.exec((repeatFor ?? "").trim());
  const columns = list ? columnsOf(questions.get(list[1])) : [];
  return columns.length ? columns : undefined;
}

/** The text between a CEL string's quotes as the text it stands for (its escapes are JSON's), or null. */
function unquoted(text: string): string | null {
  try {
    return JSON.parse(`"${text}"`) as string;
  } catch {
    return null;
  }
}

/** The value a printed expression gives, as shown: labels for a name standing on its own, else the value itself. */
export function shownAs(expr: string, value: unknown, context: LabelContext): unknown {
  const text = expr.trim();
  const answer = ANSWER.exec(text);
  if (answer) {
    const question = context.questions.get(answer[1]);
    return question ? shown(question.type, settingsOf(question.type, question.settings), value) : value;
  }
  const item = ITEM.exec(text);
  if (item) return cell(context.item?.find((c) => c.key === item[1]), value);
  const one = CELL.exec(text);
  if (one) return cell(columnsOf(context.questions.get(one[1])).find((c) => c.key === one[2]), value);
  const joined = JOINED.exec(text);
  if (joined) {
    const question = context.questions.get(joined[1]);
    const chosen = context.answer(joined[1]);
    const between = unquoted(joined[2] ?? "");
    if (question?.type !== "multi_select" || !Array.isArray(chosen) || between === null) return value;
    return (shown(question.type, settingsOf(question.type, question.settings), chosen) as unknown[]).join(between);
  }
  const every = EVERY.exec(text);
  if (every) {
    const column = columnsOf(context.questions.get(every[1])).find((c) => c.key === every[3]);
    const rows = context.answer(every[1]);
    const between = unquoted(every[4]);
    if (!column || column.type !== "dropdown" || !Array.isArray(rows) || between === null) return value;
    return rows.map((row) => String(cell(column, (row as Record<string, unknown> | null)?.[column.key]) ?? "")).join(between);
  }
  return value;
}
