<script lang="ts">
  import type { NameEntry } from "#lib/templates/catalogue.js";
  import { NO_VALUE, OPS, type Compare, type Op } from "#lib/templates/rules.js";
  import CompareRow from "./CompareRow.svelte";
  import LiteralInput from "./LiteralInput.svelte";

  // One comparison: a name, how it's compared, and with what. For a repeating group,
  // a condition on its rows' columns sits inside it.
  let { compare = $bindable(), entries, label = "Condition" }: {
    compare: Compare;
    entries: NameEntry[];
    label?: string;
  } = $props();

  const entry = $derived(entries.find((e) => e.name === compare.name));
  const shape = $derived(entry?.shape ?? "text");
  const ops = $derived(OPS[shape]);
  const groups = $derived([...new Set(entries.filter((e) => e.shape !== "other").map((e) => e.group))]);
  const rowEntries = $derived(
    (entry?.columns ?? []).map((c) => ({ name: `row.${c.key}`, label: c.label, group: "Columns", type: "", shape: c.shape, choices: c.choices })),
  );

  function pick(name: string) {
    const next = entries.find((e) => e.name === name);
    const op = OPS[next?.shape ?? "text"][0]?.op ?? "eq";
    compare = { kind: "compare", name, op };
  }

  function setOp(op: Op) {
    const next: Compare = { kind: "compare", name: compare.name, op };
    if (op === "any_row" || op === "every_row" || op === "rows_where_at_least") {
      const first = rowEntries[0];
      next.row = compare.row ?? { kind: "compare", name: first?.name ?? "row.value", op: OPS[first?.shape ?? "text"][0].op };
    }
    if (op === "rows_at_least" || op === "rows_where_at_least") next.count = compare.count ?? 1;
    if (op === "between" || (!NO_VALUE.has(op) && compare.value !== undefined && OPS[shape].some((o) => o.op === compare.op))) {
      next.value = compare.value;
    }
    compare = next;
  }
</script>

<div class="compare">
  <select class="input name" aria-label="{label}: what to check" value={compare.name} onchange={(e) => pick(e.currentTarget.value)}>
    {#if !entry}<option value={compare.name}>{compare.name}</option>{/if}
    {#each groups as group (group)}
      <optgroup label={group}>
        {#each entries.filter((e) => e.group === group && e.shape !== "other") as e (e.name)}
          <option value={e.name}>{e.label}</option>
        {/each}
      </optgroup>
    {/each}
  </select>
  <select class="input op" aria-label="{label}: how" value={compare.op} onchange={(e) => setOp(e.currentTarget.value as Op)}>
    {#each ops as o (o.op)}<option value={o.op}>{o.label}</option>{/each}
  </select>
  {#if compare.op === "between"}
    <span class="pair">
      <LiteralInput bind:value={compare.value} {shape} label="{label}: from" />
      <span class="small muted">and</span>
      <LiteralInput bind:value={compare.until} {shape} label="{label}: to" />
    </span>
  {:else if compare.op === "one_of"}
    {#if entry?.choices?.length}
      <span class="choices">
        {#each entry.choices as choice (choice.value)}
          <label class="check small"><input type="checkbox" checked={compare.values?.includes(choice.value)}
            onchange={(e) => (compare.values = e.currentTarget.checked ? [...(compare.values ?? []), choice.value] : (compare.values ?? []).filter((v) => v !== choice.value))} /> {choice.label}</label>
        {/each}
      </span>
    {:else}
      <input class="input" aria-label="{label}: values, separated by commas" value={(compare.values ?? []).join(", ")}
        oninput={(e) => (compare.values = e.currentTarget.value.split(",").map((v) => v.trim()).filter(Boolean))} />
    {/if}
  {:else if compare.op === "rows_at_least" || compare.op === "rows_where_at_least"}
    <input class="input count" type="number" min="0" aria-label="{label}: how many rows" value={compare.count ?? 1}
      oninput={(e) => (compare.count = Number(e.currentTarget.value) || 0)} />
  {:else if !NO_VALUE.has(compare.op) && compare.op !== "any_row" && compare.op !== "every_row"}
    <LiteralInput bind:value={compare.value} shape={compare.op === "includes" || compare.op === "excludes" || ["contains", "starts", "ends", "matches"].includes(compare.op) ? "text" : shape}
      choices={["eq", "ne", "includes", "excludes"].includes(compare.op) ? entry?.choices : undefined} label="{label}: value" />
  {/if}
</div>
{#if compare.row}
  <div class="row-condition">
    <span class="small muted">where</span>
    <CompareRow bind:compare={compare.row} entries={rowEntries} label="{label}, row" />
  </div>
{/if}

<style>
  .compare {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    align-items: center;
  }
  .name {
    flex: 1 1 160px;
    max-width: 100%;
  }
  .op {
    flex: 0 1 150px;
  }
  .compare > :global(.input:last-child:not(.op):not(.name)) {
    flex: 1 1 120px;
  }
  .pair {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .choices {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-3);
  }
  .count {
    width: 80px;
  }
  .row-condition {
    display: grid;
    gap: var(--space-1);
    margin: var(--space-1) 0 0 var(--space-4);
    padding-left: var(--space-2);
    border-left: 2px solid var(--border);
  }
</style>
