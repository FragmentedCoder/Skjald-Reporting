<script lang="ts">
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import type { NameEntry } from "#lib/templates/catalogue.js";
  import { OPS, type Compare, type Condition, type Group } from "#lib/templates/rules.js";
  import CompareRow from "./CompareRow.svelte";
  import ConditionEditor from "./ConditionEditor.svelte";

  // A group of conditions: all of them, any of them or exactly one (AND, OR, XOR), each
  // a comparison, a group of its own, or either turned around (NOT).
  let { condition = $bindable(), entries, depth = 0, label = "Condition", onremove }: {
    condition: Group;
    entries: NameEntry[];
    depth?: number;
    label?: string;
    onremove?: () => void;
  } = $props();

  function blank(): Compare {
    const first = entries.find((e) => e.group === "Answers" && e.shape !== "other") ?? entries.find((e) => e.shape !== "other");
    return { kind: "compare", name: first?.name ?? "", op: OPS[first?.shape ?? "text"][0]?.op ?? "eq" };
  }

  const inner = (item: Condition): Condition => (item.kind === "not" ? item.item : item);
  const asGroup = (item: Condition): Group => (item.kind === "compare" || item.kind === "not" ? { kind: "all", items: [item] } : item);

  function turn(index: number) {
    const item = condition.items[index];
    condition.items[index] = item.kind === "not" ? item.item : { kind: "not", item };
  }
</script>

<div class="group" class:nested={depth > 0}>
  {#if condition.items.length > 1 || depth > 0}
    <div class="group-head">
      <select class="input combine" aria-label="{label}: how they combine" bind:value={condition.kind}>
        <option value="all">All of these (AND)</option>
        <option value="any">Any of these (OR)</option>
        <option value="one">Exactly one of these (XOR)</option>
      </select>
      {#if onremove}
        <button class="mini" type="button" aria-label="Remove this group" title="Remove this group" onclick={onremove}><X size={14} aria-hidden="true" /></button>
      {/if}
    </div>
  {/if}
  {#each condition.items as item, index (index)}
    {@const shown = inner(item)}
    <div class="item">
      <button class="not" type="button" aria-pressed={item.kind === "not"} title="Turn it around (NOT)"
        aria-label="{label} {index + 1}: not" onclick={() => turn(index)}>Not</button>
      <div class="body">
        {#if shown.kind === "compare"}
          {#if item.kind === "not"}
            <CompareRow bind:compare={() => (item.item as Compare), (v) => (item.item = v)} {entries} label="{label} {index + 1}" />
          {:else}
            <CompareRow bind:compare={() => item as Compare, (v) => (condition.items[index] = v)} {entries} label="{label} {index + 1}" />
          {/if}
        {:else}
          <ConditionEditor bind:condition={() => asGroup(shown), (v) => (item.kind === "not" ? (item.item = v) : (condition.items[index] = v))}
            {entries} depth={depth + 1} label="{label} {index + 1}" onremove={() => condition.items.splice(index, 1)} />
        {/if}
      </div>
      {#if shown.kind === "compare"}
        <button class="mini" type="button" aria-label="Remove {label.toLowerCase()} {index + 1}" title="Remove" onclick={() => condition.items.splice(index, 1)}><X size={14} aria-hidden="true" /></button>
      {/if}
    </div>
  {/each}
  <div class="add">
    <button class="link-button small" type="button" onclick={() => condition.items.push(blank())}><Plus size={14} aria-hidden="true" /> Add a condition</button>
    {#if depth < 2}
      <button class="link-button small" type="button" onclick={() => condition.items.push({ kind: "any", items: [blank()] })}><Plus size={14} aria-hidden="true" /> Add a group</button>
    {/if}
  </div>
</div>

<style>
  .group {
    display: grid;
    gap: var(--space-2);
  }
  .nested {
    padding: var(--space-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--bg);
  }
  .group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .combine {
    width: auto;
  }
  .item {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: var(--space-1);
    align-items: start;
  }
  .not {
    margin-top: 6px;
    padding: 2px 6px;
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    background: transparent;
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
  }
  .not[aria-pressed="true"] {
    border-color: var(--warning-text);
    background: var(--warning-bg);
    color: var(--warning-text);
  }
  .mini {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    margin-top: 6px;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .mini:hover {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .add {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }
  .add :global(svg) {
    vertical-align: -2px;
  }
</style>
