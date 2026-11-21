import { describe, expect, it } from "vitest";
import shared from "../../../../shared/templates/limits.json";
import { MAX_BLOCK_DEPTH, MAX_BLOCKS, MAX_IN_ONE_LIST, MAX_QUESTIONS, MAX_STEPS, noRoomForBlock, noRoomForQuestion, noRoomForStep } from "./limits";
import type { Block, Question, TemplateContent } from "./types";

const template = (blocks: number, questions: number): TemplateContent => ({
  schema: 1,
  settings: {} as TemplateContent["settings"],
  form: Array.from({ length: Math.max(1, Math.ceil(questions / 250)) }, (_, s) => ({
    id: `s_step${s}`, title: "Step", help: "", visible_when: null,
    questions: Array.from({ length: Math.min(250, questions - s * 250) }, (_, i) => ({ id: `q_q${s}x${i}`, type: "text" }) as Question),
  })),
  layout: Array.from({ length: Math.ceil(blocks / 250) }, (_, s) => ({
    id: `b_sec${s}`, kind: "section", title: "", blocks: Array.from({ length: Math.min(249, blocks - s * 250 - 1) }, (_, i) => ({ id: `b_b${s}x${i}`, kind: "page_break" }) as Block),
  }) as Block),
  sample: { answers: {} },
});

describe("how large a template may be", () => {
  it("is what the server allows", () => {
    expect({ questions: MAX_QUESTIONS, blocks: MAX_BLOCKS, block_depth: MAX_BLOCK_DEPTH, in_one_list: MAX_IN_ONE_LIST, steps: MAX_STEPS })
      .toEqual({ questions: shared.questions, blocks: shared.blocks, block_depth: shared.block_depth, in_one_list: shared.in_one_list, steps: shared.steps });
  });

  it("has room until the last block and question, and says why not after", () => {
    const nearly = template(999, 499);
    expect(noRoomForBlock(nearly, nearly.layout)).toBeNull();
    expect(noRoomForQuestion(nearly, nearly.form[0])).toBeNull();
    const full = template(1000, 500);
    expect(noRoomForBlock(full, full.layout)).toBe("A template takes up to 1,000 blocks, and this one has them all.");
    expect(noRoomForQuestion(full, full.form[0])).toBe("A template takes up to 500 questions and headings, and this one has them all.");
  });

  it("says when one section, step or form is full", () => {
    const content = template(10, 10);
    const list = Array.from({ length: 300 }, (_, i) => ({ id: `b_x${i}`, kind: "page_break" }) as Block);
    expect(noRoomForBlock(content, list)).toBe("One section takes up to 300 blocks: put the next one in a new section.");
    const step = { ...content.form[0], questions: Array.from({ length: 300 }, (_, i) => ({ id: `q_x${i}`, type: "text" }) as Question) };
    expect(noRoomForQuestion(content, step)).toBe("One step takes up to 300 questions: put the next one in a new step.");
    expect(noRoomForStep(content)).toBeNull();
    expect(noRoomForStep({ ...content, form: Array.from({ length: 50 }, () => content.form[0]) })).toBe("A form takes up to 50 steps.");
  });
});
