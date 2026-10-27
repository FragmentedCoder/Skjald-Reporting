<script lang="ts">
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import X from "@lucide/svelte/icons/x";
  import type { Engine } from "#lib/cel/engine.js";
  import { RESERVED } from "#lib/templates/checks.js";
  import { KEY_PATTERN, usage } from "#lib/templates/edit.js";
  import { fieldType } from "#lib/templates/fields.js";
  import { questionNames } from "#lib/templates/names.js";
  import { questionsOf, type Problem, type Question, type TemplateContent } from "#lib/templates/types.js";
  import ExpressionField from "./ExpressionField.svelte";
  import TypeSettings from "./TypeSettings.svelte";
  import Where from "./Where.svelte";

  // Everything about the selected question: what the technician sees, its variable
  // name, its rules, and where the PDF prints it.
  let {
    question,
    content,
    engine,
    problems,
    first,
    last,
    onrename,
    onremove,
    onmove,
  }: {
    question: Question;
    content: TemplateContent;
    engine: Engine;
    problems: Problem[];
    first: boolean;
    last: boolean;
    onrename: (key: string) => void;
    onremove: () => void;
    onmove: (by: number) => void;
  } = $props();

  const type = $derived(fieldType(question.type));
  const id = $derived(`q-${question.id}`);
  const used = $derived(usage(content, question));
  const own = $derived(question.key ? questionNames(question)[`answers.${question.key}`] ?? null : null);
  const names = $derived(Object.keys(questionNames(question)));

  // What's typed, until Rename: the question's own name again when another is selected.
  let key = $derived(question.key ?? "");
  const keyProblem = $derived.by(() => {
    if (!type.asks || key === (question.key ?? "")) return null;
    if (!KEY_PATTERN.test(key)) return "Use small letters, digits and _, starting with a letter.";
    if (RESERVED.has(key)) return `${key} is a reserved word in expressions.`;
    if (questionsOf(content).some((q) => q.id !== question.id && q.key === key)) return `Another question already uses ${key}.`;
    return null;
  });
  const problem = (field: string) => problems.find((p) => p.field === field)?.message ?? null;
  const blockName = (kind: string, title: string | undefined) =>
    title ? `“${title}”` : `${kind.replace("_", " ")} block`;
</script>

<div class="panel-head">
  <span class="type"><type.icon size={16} aria-hidden="true" /> {type.label}</span>
  <span class="head-actions">
    <button class="mini" type="button" aria-label="Move up" title="Move up" disabled={first} onclick={() => onmove(-1)}><ArrowUp size={16} aria-hidden="true" /></button>
    <button class="mini" type="button" aria-label="Move down" title="Move down" disabled={last} onclick={() => onmove(1)}><ArrowDown size={16} aria-hidden="true" /></button>
    <button class="mini" type="button" aria-label="Remove the question" title="Remove" onclick={onremove}><X size={16} aria-hidden="true" /></button>
  </span>
</div>

<section class="group" aria-labelledby="{id}-form">
  <div class="group-head"><h3 id="{id}-form">In the form</h3><Where form /></div>
  <div class="field">
    <label for="{id}-label">{question.type === "heading" ? "Heading" : "Question"}</label>
    <input id="{id}-label" class="input" bind:value={question.label} maxlength="300" required />
  </div>
  <div class="field">
    <label for="{id}-help">Help for the technician <span class="muted">(optional)</span></label>
    <textarea id="{id}-help" class="input" rows="2" bind:value={question.help} maxlength="2000"></textarea>
    <span class="hint">Shown under the question. Never printed.</span>
  </div>
  {#if type.asks && question.type !== "calculated"}
    <label class="check"><input type="checkbox" bind:checked={question.required} /> Required before the report goes for review</label>
  {/if}
  <TypeSettings {question} />
</section>

{#if type.asks}
  <section class="group" aria-labelledby="{id}-variable">
    <div class="group-head"><h3 id="{id}-variable">Variable name</h3><Where builder /></div>
    <div class="field">
      <label for="{id}-key">Rules and text read the answer as</label>
      <div class="key-line">
        <span class="mono prefix">answers.</span>
        <input id="{id}-key" class="input mono" bind:value={key} maxlength="50" spellcheck="false" autocomplete="off"
          aria-invalid={keyProblem ? "true" : undefined}
          onkeydown={(e) => { if (e.key === "Enter" && !keyProblem && key !== question.key) onrename(key); }} />
        <button class="button button-secondary" type="button" disabled={!!keyProblem || key === (question.key ?? "")}
          onclick={() => onrename(key)}>Rename</button>
      </div>
      <span class="hint" class:error={keyProblem || problem("key")}>
        {keyProblem ?? problem("key") ?? "Renaming changes every rule and text that reads it."}
      </span>
    </div>
    {#if names.length > 1 || (names.length === 1 && names[0] !== `answers.${question.key}`)}
      <p class="small muted">Gives rules: {#each names as name, i (name)}<span class="mono">{name}</span>{i < names.length - 1 ? ", " : ""}{/each}</p>
    {/if}
  </section>

  <section class="group" aria-labelledby="{id}-rules">
    <div class="group-head"><h3 id="{id}-rules">Rules</h3><Where form /></div>
    {#if question.type === "calculated"}
      <ExpressionField id="{id}-value" label="Worked out as" bind:value={question.value} {engine} expects={own}
        problem={problem("value")} rows={3} placeholder='answers.cvss >= 9.0 ? "Critical" : "Lower"'
        hint="An expression over other answers, the customer, the project or the library." />
    {/if}
    <ExpressionField id="{id}-visible" label="Show only when" bind:value={question.visible_when} {engine} expects="bool"
      problem={problem("visible_when")} placeholder="answers.attack_found" hint="Always shown when empty." />
    {#if question.type !== "calculated"}
      <ExpressionField id="{id}-required" label="Required only when" bind:value={question.required_when} {engine} expects="bool"
        problem={problem("required_when")} hint="Empty: required or not, as set above." />
      {#if own}
        <ExpressionField id="{id}-default" label="Starts as" bind:value={question.default} {engine} expects={own}
          problem={problem("default")} placeholder="customer.name" hint="A default from the customer, the project or a lookup table." />
      {/if}
      <ExpressionField id="{id}-valid" label="Valid only when" bind:value={question.valid_when} {engine} expects="bool"
        problem={problem("valid_when")} placeholder="answers.ended >= answers.started" hint="A check of the answer, beyond its type's own." />
      {#if question.valid_when}
        <div class="field">
          <label for="{id}-valid-message">Message when it isn't</label>
          <input id="{id}-valid-message" class="input" bind:value={question.valid_message} maxlength="300" />
        </div>
      {/if}
    {/if}
  </section>

  <section class="group" aria-labelledby="{id}-pdf">
    <div class="group-head"><h3 id="{id}-pdf">In the PDF</h3><Where pdf /></div>
    {#if used.blocks.length}
      <p class="small">Printed by {#each used.blocks as b, i (b.id)}{blockName(b.kind, "title" in b ? String(b.title) : undefined)}{i < used.blocks.length - 1 ? ", " : ""}{/each}.</p>
    {:else}
      <p class="small muted">No block prints this answer. Add one on the Layout tab, or use it in text and rules.</p>
    {/if}
    {#if used.expressions}
      <p class="small muted">Read by {used.expressions} rule{used.expressions === 1 ? "" : "s"} or text{used.expressions === 1 ? "" : "s"}.</p>
    {/if}
  </section>
{/if}

<style>
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--border);
  }
  .type {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    font-weight: 600;
  }
  .head-actions {
    display: flex;
  }
  .mini {
    display: grid;
    place-items: center;
    width: 30px;
    height: 30px;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .mini:hover:not(:disabled) {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .mini:disabled {
    opacity: 0.35;
    cursor: default;
  }
  .group {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--border);
  }
  .group:last-child {
    border-bottom: 0;
  }
  .group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }
  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }
  .key-line {
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }
  .key-line .input {
    flex: 1;
    min-width: 0;
  }
  .prefix {
    color: var(--text-muted);
    font-size: 13px;
  }
  .error {
    color: var(--critical-text);
  }
  p {
    margin: 0;
  }
</style>
