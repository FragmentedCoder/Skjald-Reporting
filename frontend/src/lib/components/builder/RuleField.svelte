<script lang="ts">
  import { untrack } from "svelte";
  import { Engine, ExpressionError, human } from "#lib/cel/engine.js";
  import { shapes as shapesOf, type Choice, type NameEntry } from "#lib/templates/catalogue.js";
  import {
    conditionFromCel,
    conditionToCel,
    OPS,
    shapeOf,
    valueFromCel,
    valueToCel,
    type Group,
    type ValueRule,
  } from "#lib/templates/rules.js";
  import ConditionEditor from "./ConditionEditor.svelte";
  import ValueEditor from "./ValueEditor.svelte";

  // A rule, built visually or written as CEL. Only the CEL text is stored: the visual
  // editor reads it back when it's a rule it could have written, and otherwise the
  // text is shown, to edit as text or start again visually.
  let {
    id,
    label,
    value = $bindable(),
    kind,
    expects = null,
    engine,
    entries,
    choices,
    hint = "",
    problem = null,
    optional = true,
  }: {
    id: string;
    label: string;
    value: string | null;
    /** A condition (yes or no), or a value worked out by rules. */
    kind: "condition" | "value";
    expects?: string | null;
    engine: Engine;
    entries: NameEntry[];
    choices?: Choice[];
    hint?: string;
    problem?: string | null;
    /** Whether the rule can be left out (a condition can; a calculated value can't). */
    optional?: boolean;
  } = $props();

  const shapes = $derived(shapesOf(entries));
  const result = $derived(shapeOf(expects ?? "string"));

  let mode = $state<"visual" | "text">("visual");
  // An optional value rule shows its editor once it's added, so opening a question
  // never writes a rule nobody asked for.
  let adding = $state(false);
  let condition = $state<Group>({ kind: "all", items: [] });
  let rule = $state<ValueRule>({ kind: "fixed", value: "" });
  let written: string | null = null;

  // The stored text, read into the visual form when it changes from elsewhere (a
  // rename, a reload) or when the field opens.
  $effect.pre(() => {
    const text = value;
    untrack(() => {
      if (text === written) return;
      written = text;
      if (text === null || !text.trim()) {
        adding = false;
        condition = { kind: "all", items: [] };
        rule = { kind: "fixed", value: result === "number" || result === "whole" ? 0 : result === "bool" ? false : "" };
        mode = "visual";
        return;
      }
      if (kind === "condition") {
        const read = conditionFromCel(text, shapes);
        if (read) condition = read.kind === "compare" || read.kind === "not" ? { kind: "all", items: [read] } : read;
        mode = read ? "visual" : "text";
      } else {
        const read = valueFromCel(text, result, shapes);
        if (read) rule = read;
        mode = read ? "visual" : "text";
      }
    });
  });

  const open = $derived(kind === "condition" || !optional || value !== null || adding);

  // What the visual form says, written back as text.
  $effect(() => {
    if (mode !== "visual" || !open) return;
    const text = kind === "condition"
      ? (condition.items.length ? conditionToCel($state.snapshot(condition) as Group, shapes) : null)
      : valueToCel($state.snapshot(rule) as ValueRule, result, shapes);
    untrack(() => {
      if (text === value) return;
      written = text;
      value = text;
    });
  });

  const live = $derived.by((): string | null => {
    if (!value?.trim()) return null;
    try {
      const type = engine.check(value);
      if (expects && type !== "dyn" && type !== expects) return `This should give ${human(expects)}, but gives ${human(type)}.`;
      return null;
    } catch (error) {
      return error instanceof ExpressionError ? error.message : String(error);
    }
  });
  const shown = $derived(live ?? problem);
  const readable = $derived(value === null || (kind === "condition" ? conditionFromCel(value, shapes) !== null : valueFromCel(value, result, shapes) !== null));

  function addFirst() {
    const first = entries.find((e) => e.group === "Answers" && e.shape !== "other") ?? entries.find((e) => e.shape !== "other");
    condition = { kind: "all", items: [{ kind: "compare", name: first?.name ?? "", op: OPS[first?.shape ?? "text"][0]?.op ?? "eq" }] };
  }

  function startVisual() {
    written = null;
    value = null;
  }
</script>

<div class="rule" role="group" aria-labelledby="{id}-label">
  <div class="rule-head">
    <span id="{id}-label" class="label">{label}</span>
    {#if mode === "visual"}
      <button class="link-button small" type="button" onclick={() => (mode = "text")}>Edit as text</button>
    {:else if readable}
      <button class="link-button small" type="button" onclick={() => { written = null; mode = "visual"; value = value; }}>Edit visually</button>
    {/if}
  </div>
  {#if mode === "visual"}
    {#if kind === "condition"}
      {#if condition.items.length}
        <ConditionEditor bind:condition {entries} label={label} />
      {:else}
        <p class="small muted none">{hint || "No rule."}</p>
        <button class="button button-secondary small-button" type="button" onclick={addFirst}>Add a condition</button>
      {/if}
    {:else if open}
      <ValueEditor bind:rule {result} {entries} {choices} {label} />
    {:else}
      <p class="small muted none">{hint || "No rule."}</p>
      <button class="button button-secondary small-button" type="button" onclick={() => (adding = true)}>Add a rule</button>
    {/if}
  {:else}
    <textarea id="{id}-text" class="input mono" rows="3" spellcheck="false" autocomplete="off" aria-labelledby="{id}-label"
      aria-invalid={shown ? "true" : undefined}
      value={value ?? ""} oninput={(e) => { value = e.currentTarget.value === "" ? null : e.currentTarget.value; written = value; }}></textarea>
    {#if !readable}
      <p class="small muted">Written by hand, so it's edited as text. <button class="link-button" type="button" onclick={startVisual}>Start again visually</button></p>
    {/if}
  {/if}
  {#if shown}<p class="small error" role="status">{shown}</p>{:else if value && mode === "visual"}<p class="small muted mono cel">{value}</p>{/if}
  {#if !optional && !value}<p class="small error">This needs a rule.</p>{/if}
</div>

<style>
  .rule {
    display: grid;
    gap: var(--space-2);
  }
  .rule-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .label {
    font-size: 14px;
    font-weight: 600;
  }
  .none,
  p {
    margin: 0;
  }
  textarea {
    font-size: 13px;
  }
  .error {
    color: var(--critical-text);
  }
  .cel {
    overflow-wrap: anywhere;
  }
  .small-button {
    justify-self: start;
    padding: 4px 10px;
    font-size: 13px;
  }
</style>
