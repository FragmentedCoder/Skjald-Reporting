<script lang="ts">
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import X from "@lucide/svelte/icons/x";
  import type { Engine } from "#lib/cel/engine.js";
  import type { Problem, Step } from "#lib/templates/types.js";
  import ExpressionField from "./ExpressionField.svelte";
  import Where from "./Where.svelte";

  // A step of the technician's form: its title, what it explains, and when it shows.
  let { step, number, engine, problems, first, last, only, onremove, onmove }: {
    step: Step;
    number: number;
    engine: Engine;
    problems: Problem[];
    first: boolean;
    last: boolean;
    only: boolean;
    onremove: () => void;
    onmove: (by: number) => void;
  } = $props();

  const id = $derived(`s-${step.id}`);
</script>

<div class="panel-head">
  <span class="type">Step {number}</span>
  <span class="head-actions">
    <button class="mini" type="button" aria-label="Move the step up" title="Move up" disabled={first} onclick={() => onmove(-1)}><ArrowUp size={16} aria-hidden="true" /></button>
    <button class="mini" type="button" aria-label="Move the step down" title="Move down" disabled={last} onclick={() => onmove(1)}><ArrowDown size={16} aria-hidden="true" /></button>
    <button class="mini" type="button" aria-label="Remove the step" title={only ? "A form needs a step" : "Remove"} disabled={only} onclick={onremove}><X size={16} aria-hidden="true" /></button>
  </span>
</div>

<section class="group" aria-labelledby="{id}-form">
  <div class="group-head"><h3 id="{id}-form">In the form</h3><Where form /></div>
  <div class="field">
    <label for="{id}-title">Title</label>
    <input id="{id}-title" class="input" bind:value={step.title} maxlength="200" required />
  </div>
  <div class="field">
    <label for="{id}-help">What the technician should know <span class="muted">(optional)</span></label>
    <textarea id="{id}-help" class="input" rows="3" bind:value={step.help} maxlength="2000"></textarea>
    <span class="hint">Shown at the top of the step. Never printed.</span>
  </div>
  <ExpressionField id="{id}-visible" label="Show only when" bind:value={step.visible_when} {engine} expects="bool"
    problem={problems.find((p) => p.field === "visible_when")?.message ?? null} hint="Always shown when empty." />
</section>

<style>
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--border);
  }
  .type {
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
  }
  .group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }
</style>
