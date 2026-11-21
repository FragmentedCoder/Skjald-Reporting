// How large a template may be: the server's limits (backend/app/templates/content.py),
// checked here before something is added, so a draft never grows past what can be
// saved. shared/templates/limits.json holds both sides to the same numbers.

import { blocksOf, type Block, type Step, type TemplateContent } from "./types";

export const MAX_QUESTIONS = 500;
export const MAX_BLOCKS = 1000;
export const MAX_BLOCK_DEPTH = 10;
/** Blocks in one section, column or case, and questions in one step. */
export const MAX_IN_ONE_LIST = 300;
export const MAX_STEPS = 50;

const count = (n: number) => n.toLocaleString("en-GB");

/** Why no block can be added to this list, or null when there's room. */
export function noRoomForBlock(content: TemplateContent, list: Block[]): string | null {
  if (blocksOf(content.layout).length >= MAX_BLOCKS) return `A template takes up to ${count(MAX_BLOCKS)} blocks, and this one has them all.`;
  if (list.length >= MAX_IN_ONE_LIST) return `One section takes up to ${MAX_IN_ONE_LIST} blocks: put the next one in a new section.`;
  return null;
}

/** Why no question can be added to this step, or null when there's room. */
export function noRoomForQuestion(content: TemplateContent, step: Step): string | null {
  const asked = content.form.reduce((n, s) => n + s.questions.length, 0);
  if (asked >= MAX_QUESTIONS) return `A template takes up to ${count(MAX_QUESTIONS)} questions and headings, and this one has them all.`;
  if (step.questions.length >= MAX_IN_ONE_LIST) return `One step takes up to ${MAX_IN_ONE_LIST} questions: put the next one in a new step.`;
  return null;
}

/** Why no step can be added, or null when there's room. */
export function noRoomForStep(content: TemplateContent): string | null {
  return content.form.length >= MAX_STEPS ? `A form takes up to ${MAX_STEPS} steps.` : null;
}
