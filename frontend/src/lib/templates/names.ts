// The names a template's expressions can read, and their types: the browser's copy of
// backend/app/templates/names.py, worked out again as the designer edits. Besides the
// template's answers there are the report's context (shared/templates/names.json) and
// the shared library (vars.<name>, text.<name>).

import { contextNames } from "#lib/shared.js";
import { fieldType, settingsOf } from "./fields";
import { questionsOf, type Question, type TemplateContent } from "./types";

export interface ContextName {
  name: string;
  type: string;
  description: string;
  example: unknown;
}

export interface ContextGroup {
  name: string;
  label: string;
  source: string;
  names: ContextName[];
}

export const CONTEXT_GROUPS = contextNames.groups as ContextGroup[];
export const CONTEXT: Record<string, string> = Object.fromEntries(
  CONTEXT_GROUPS.flatMap((group) => group.names.map((n) => [n.name, n.type])),
);
export const CONTEXT_ROOTS = new Set(CONTEXT_GROUPS.map((group) => group.name));

/** Inside a section repeated for each item of a list. */
export const ITEM = { item: "map<string, dyn>" };

/** The names one question gives expressions. */
export function questionNames(question: Question): Record<string, string> {
  if (question.key === null) return {};
  const type = fieldType(question.type);
  const names = type.names(settingsOf(question.type, question.settings));
  return Object.fromEntries(Object.entries(names).map(([suffix, t]) => [`answers.${question.key}${suffix}`, t]));
}

/**
 * Every name the template's expressions can read, with its type, sorted. When two
 * questions share a variable name the first one's names count; the duplicate is a
 * problem of its own.
 */
export function declarations(content: TemplateContent, library: Record<string, string> = {}): Record<string, string> {
  const names: Record<string, string> = { ...CONTEXT };
  for (const question of questionsOf(content)) {
    for (const [name, type] of Object.entries(questionNames(question))) {
      if (!(name in names)) names[name] = type;
    }
  }
  Object.assign(names, library);
  return Object.fromEntries(Object.entries(names).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}
