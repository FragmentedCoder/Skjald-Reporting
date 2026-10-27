<script lang="ts">
  import Plus from "@lucide/svelte/icons/plus";
  import { tick } from "svelte";
  import { dndzone, type DndEvent } from "svelte-dnd-action";
  import { Engine } from "#lib/cel/engine.js";
  import Palette, { type Dragged, type PaletteEntry } from "#lib/components/builder/Palette.svelte";
  import Dialog from "#lib/components/Dialog.svelte";
  import ProblemList from "#lib/components/builder/ProblemList.svelte";
  import QuestionPanel from "#lib/components/builder/QuestionPanel.svelte";
  import StepPanel from "#lib/components/builder/StepPanel.svelte";
  import Where from "#lib/components/builder/Where.svelte";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import { newQuestion, newStep, renameKey, usage } from "#lib/templates/edit.js";
  import { FIELD_GROUPS, FIELD_TYPES, fieldType } from "#lib/templates/fields.js";
  import { catalogue } from "#lib/templates/catalogue.js";
  import { declarations } from "#lib/templates/names.js";
  import type { Problem, Question, Step, TemplateContent } from "#lib/templates/types.js";

  // The Questions tab: the technician's form, step by step. Field types are dragged
  // in from the palette, or clicked to add after what's selected; questions are
  // dragged between steps, or moved with the arrows in their panel.
  const draft = useDraft();
  const content = $derived(draft.content as TemplateContent);

  const palette: PaletteEntry[] = FIELD_GROUPS.flatMap((group) =>
    Object.entries(FIELD_TYPES).filter(([, t]) => t.group === group).map(([kind, t]) => ({ kind, label: t.label, hint: t.hint, icon: t.icon, group })),
  );

  // The names expressions can read; the engine is made again only when they change.
  const names = $derived(JSON.stringify(declarations(content)));
  const engine = $derived(new Engine(JSON.parse(names), { language: content.settings.language }));
  // The names rules can use, labelled for the rule editors.
  const entries = $derived(catalogue(content));

  const selection = $derived(draft.selection);
  const where = $derived.by(() => {
    if (!selection) return null;
    for (const [s, step] of content.form.entries()) {
      if (selection.kind === "step" && step.id === selection.id) return { step, stepIndex: s, question: null, index: -1 };
      const index = step.questions.findIndex((q) => q.id === selection.id);
      if (selection.kind === "question" && index >= 0) return { step, stepIndex: s, question: step.questions[index], index };
    }
    return null;
  });

  function select(kind: "step" | "question", id: string) {
    draft.selection = { kind, id };
  }

  async function focusPanel() {
    await tick();
    document.querySelector<HTMLElement>(".panel input, .panel textarea")?.focus();
  }

  function add(kind: string) {
    if (draft.readonly) return;
    const question = newQuestion(kind, content);
    const step = where?.step ?? content.form[content.form.length - 1];
    const at = where?.question ? where.index + 1 : step.questions.length;
    step.questions.splice(at, 0, question);
    select("question", question.id);
    void focusPanel();
  }

  function addStep() {
    const step = newStep();
    content.form.push(step);
    select("step", step.id);
  }

  type Item = Question | Dragged;

  function consider(step: Step, event: CustomEvent<DndEvent<Item>>) {
    step.questions = event.detail.items as Question[];
  }

  function finalize(step: Step, event: CustomEvent<DndEvent<Item>>) {
    let added: Question | null = null;
    step.questions = event.detail.items.map((item) => {
      if ("palette" in item) {
        added = newQuestion(item.kind, content);
        return added;
      }
      return item;
    });
    if (added) select("question", (added as Question).id);
  }

  function rename(question: Question, key: string) {
    if (!question.key) return;
    draft.content = renameKey($state.snapshot(content) as TemplateContent, question.key, key);
  }

  // Removing something that's used, or a step with questions, asks first.
  let confirming = $state(false);
  let confirmText = $state("");
  let confirmed: () => void = () => {};

  function ask(text: string, then: () => void) {
    confirmText = text;
    confirmed = then;
    confirming = true;
  }

  function removeQuestion(step: Step, question: Question) {
    const remove = () => {
      step.questions = step.questions.filter((q) => q.id !== question.id);
      draft.selection = { kind: "step", id: step.id };
    };
    const used = usage(content, question);
    if (!used.blocks.length && !used.expressions) return remove();
    const parts = [
      used.blocks.length ? `${used.blocks.length} block${used.blocks.length === 1 ? "" : "s"} print${used.blocks.length === 1 ? "s" : ""} it` : "",
      used.expressions ? `${used.expressions} rule${used.expressions === 1 ? "" : "s"} or text${used.expressions === 1 ? "" : "s"} read${used.expressions === 1 ? "s" : ""} it` : "",
    ].filter(Boolean);
    ask(`${parts.join(" and ")}; each will show a problem until it's changed.`, remove);
  }

  function moveQuestion(by: number) {
    if (!where?.question) return;
    const { step, stepIndex, index, question } = where;
    const target = index + by;
    if (target >= 0 && target < step.questions.length) {
      step.questions.splice(index, 1);
      step.questions.splice(target, 0, question);
    } else {
      // Past the end of its step: into the next or previous one.
      const other = content.form[stepIndex + by];
      if (!other) return;
      step.questions.splice(index, 1);
      if (by > 0) other.questions.unshift(question);
      else other.questions.push(question);
    }
  }

  function moveStep(by: number) {
    if (!where || where.question) return;
    const { stepIndex, step } = where;
    content.form.splice(stepIndex, 1);
    content.form.splice(stepIndex + by, 0, step);
  }

  function removeStep() {
    if (!where || where.question || content.form.length === 1) return;
    const { step, stepIndex } = where;
    const remove = () => {
      content.form.splice(stepIndex, 1);
      draft.selection = null;
    };
    if (!step.questions.length) return remove();
    ask(`“${step.title}” has ${step.questions.length} question${step.questions.length === 1 ? "" : "s"}, which go with it.`, remove);
  }

  function show(problem: Problem) {
    const isStep = content.form.some((s) => s.id === problem.element);
    const isQuestion = content.form.some((s) => s.questions.some((q) => q.id === problem.element));
    if (isStep || isQuestion) {
      select(isStep ? "step" : "question", problem.element);
      void focusPanel();
    }
  }

  const printedBy = (q: Question) => usage(content, q).blocks.length > 0;
  const total = $derived(content.form.reduce((n, s) => n + s.questions.length, 0));
  const lastQuestion = (stepIndex: number, index: number) =>
    stepIndex === content.form.length - 1 && index === content.form[stepIndex].questions.length - 1;
</script>

{#if draft.readonly}
  <p class="alert alert-info small">This is version {draft.shownVersion}, which reports use. Choose Edit to change it in a new draft.</p>
{/if}

<div class="workspace" class:readonly={draft.readonly}>
  {#if !draft.readonly}
    <Palette entries={palette} type="questions" title="Field types" onadd={add} />
  {/if}

  <section class="canvas" aria-labelledby="form-title">
    <div class="intro">
      <h2 id="form-title" class="section-title">The form <Where form /></h2>
      <p class="small muted">
        What the technician fills in, one step at a time: {content.form.length} step{content.form.length === 1 ? "" : "s"}, {total} question{total === 1 ? "" : "s"}.
        Nothing is printed unless a block on the Layout tab, or a text, uses it.
      </p>
    </div>

    {#each content.form as step, s (step.id)}
      {@const stepProblems = draft.problemsFor(step.id).length}
      <article class="step" class:selected={selection?.id === step.id}>
        <button class="step-head" type="button" onclick={() => select("step", step.id)} aria-label="Step {s + 1}: {step.title}, edit">
          <span class="overline">Step {s + 1}</span>
          <span class="step-title">{step.title}</span>
          {#if step.visible_when}<span class="rule small">Shown when a rule says so</span>{/if}
          {#if stepProblems}<span class="flag small">{stepProblems} problem{stepProblems === 1 ? "" : "s"}</span>{/if}
        </button>
        <ol class="questions" aria-label="Questions in step {s + 1}"
          use:dndzone={{ items: step.questions, type: "questions", flipDurationMs: 150, dragDisabled: draft.readonly,
                         dropTargetStyle: { outline: "2px dashed var(--link)", outlineOffset: "2px" } }}
          onconsider={(e) => consider(step, e)} onfinalize={(e) => finalize(step, e)}>
          {#each step.questions as q, i (q.id)}
            {#if "palette" in q}
              <li class="question shadow"><span class="label">{(q as unknown as Dragged).label}</span></li>
            {:else}
              {@const type = fieldType(q.type)}
              {@const flagged = draft.problemsFor(q.id).length}
              <li class="question" class:selected={selection?.id === q.id} class:heading={q.type === "heading"} data-question={q.id}>
                <button class="pick" type="button" onclick={() => select("question", q.id)}
                  aria-label="{q.label}, {type.label}, edit" aria-describedby="meta-{q.id}">
                  <span class="pick-in">
                    <span class="icon" aria-hidden="true"><type.icon size={16} aria-hidden="true" /></span>
                    <span class="body">
                      <span class="label">{q.label}{q.required ? " *" : ""}</span>
                      <span class="meta small" id="meta-{q.id}">
                        {#if q.key}<span class="mono">answers.{q.key}</span> · {/if}{type.label}
                        {#if q.visible_when} · shown when a rule says so{/if}
                      </span>
                    </span>
                    <span class="chips">
                      {#if flagged}<span class="flag small">{flagged} problem{flagged === 1 ? "" : "s"}</span>{/if}
                      <Where form={q.type !== "calculated" || Boolean(q.settings.show_in_form)} pdf={printedBy(q)} />
                    </span>
                  </span>
                </button>
              </li>
            {/if}
          {/each}
        </ol>
        {#if !step.questions.length}
          <p class="empty small muted">Drag a field type here, or select this step and click one.</p>
        {/if}
      </article>
    {/each}

    {#if !draft.readonly}
      <button class="button button-secondary add-step" type="button" onclick={addStep}><Plus size={16} aria-hidden="true" /> Add a step</button>
    {/if}
  </section>

  <aside class="panel" aria-label="Settings of what's selected">
    <fieldset class="unstyled" disabled={draft.readonly}>
      {#if where?.question}
        {@const q = where.question}
        <QuestionPanel question={q} {content} {engine} {entries} problems={draft.problemsFor(q.id)}
          first={where.stepIndex === 0 && where.index === 0} last={lastQuestion(where.stepIndex, where.index)}
          onrename={(key) => rename(q, key)} onremove={() => removeQuestion(where.step, q)} onmove={moveQuestion} />
      {:else if where}
        <StepPanel step={where.step} number={where.stepIndex + 1} {engine} {entries} problems={draft.problemsFor(where.step.id)}
          first={where.stepIndex === 0} last={where.stepIndex === content.form.length - 1} only={content.form.length === 1}
          onremove={removeStep} onmove={moveStep} />
      {:else}
        <p class="small muted">Select a step or a question to change it.</p>
      {/if}
    </fieldset>
  </aside>
</div>

{#if !draft.readonly}
  <ProblemList problems={draft.problems} {content} onselect={show} />
{/if}

<Dialog bind:open={confirming} title="Remove it?">
  <p>{confirmText}</p>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (confirming = false)}>Keep it</button>
    <button class="button button-primary" type="button" onclick={() => { confirming = false; confirmed(); }}>Remove</button>
  {/snippet}
</Dialog>

<style>
  .workspace {
    display: grid;
    grid-template-columns: 210px minmax(0, 1fr) minmax(290px, 360px);
    gap: var(--space-4);
    align-items: start;
    margin-top: var(--space-4);
  }
  .workspace.readonly {
    grid-template-columns: minmax(0, 1fr) minmax(290px, 360px);
  }
  .intro p {
    margin: var(--space-1) 0 var(--space-3);
  }
  .section-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .step {
    margin-bottom: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .step.selected {
    border-color: var(--link);
  }
  .step-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-2);
    width: 100%;
    margin-bottom: var(--space-2);
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }
  .overline {
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .step-title {
    font-family: var(--font-display);
    font-size: 20px;
  }
  .rule {
    color: var(--text-muted);
  }
  .flag {
    padding: 0 8px;
    border-radius: var(--radius-pill);
    background: var(--warning-bg);
    color: var(--warning-text);
    font-weight: 600;
  }
  .questions {
    display: grid;
    gap: var(--space-1);
    min-height: 44px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .question {
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--bg);
  }
  .question.selected {
    border-color: var(--link);
    box-shadow: 0 0 0 1px var(--link);
  }
  .question.heading {
    background: var(--surface-subtle);
  }
  .question.shadow {
    padding: var(--space-2) var(--space-3);
    border-style: dashed;
    color: var(--text-muted);
  }
  .pick {
    display: block;
    width: 100%;
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    text-align: left;
    cursor: grab;
  }
  .pick-in {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
  }
  .icon {
    display: grid;
    flex: none;
    place-items: center;
    width: 30px;
    height: 30px;
    border-radius: var(--radius-sm);
    background: var(--surface-subtle);
  }
  .body {
    display: grid;
    flex: 1;
    min-width: 0;
  }
  .label {
    font-weight: 600;
  }
  .meta {
    overflow: hidden;
    color: var(--text-muted);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-1);
  }
  .empty {
    margin: var(--space-2) 0 0;
    padding: var(--space-3);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-md);
    text-align: center;
  }
  .panel {
    position: sticky;
    top: var(--space-4);
    max-height: calc(100vh - 2 * var(--space-4));
    overflow-y: auto;
    padding: var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .unstyled {
    min-width: 0;
    margin: 0;
    padding: 0;
    border: 0;
  }
  @media (max-width: 1100px) {
    .workspace,
    .workspace.readonly {
      grid-template-columns: minmax(0, 1fr);
    }
    .panel {
      position: static;
      max-height: none;
    }
  }
</style>
