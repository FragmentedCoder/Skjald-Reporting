<script lang="ts">
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import type { TableValue } from "#lib/library.js";

  // A data table: a key column, and value columns that lookup() reads by name.
  let { value = $bindable() }: { value: TableValue } = $props();

  // Rows as a list while they're edited, so keys can be typed freely.
  let rows = $state(Object.entries(value.rows).map(([key, cells]) => ({ key, cells: [...cells] })));

  $effect(() => {
    const next: Record<string, string[]> = {};
    for (const row of rows) if (row.key.trim()) next[row.key.trim()] = row.cells.map((c) => c ?? "");
    value.rows = next;
  });

  function addColumn() {
    value.columns.push(`Column ${value.columns.length + 1}`);
    for (const row of rows) row.cells.push("");
  }

  function removeColumn(index: number) {
    value.columns.splice(index, 1);
    for (const row of rows) row.cells.splice(index, 1);
  }

  const duplicates = $derived(new Set(rows.map((r) => r.key.trim()).filter((k, i, all) => k && all.indexOf(k) !== i)));
</script>

<div class="table-editor">
  <div class="grid-wrap">
    <table>
      <thead>
        <tr>
          <th><input class="input" aria-label="Key column's name" bind:value={value.key_label} maxlength="100" /></th>
          {#each value.columns as _column, c (c)}
            <th>
              <span class="head">
                <input class="input" aria-label="Column {c + 1}'s name" bind:value={value.columns[c]} maxlength="100" />
                <button class="mini" type="button" aria-label="Remove column {c + 1}" disabled={value.columns.length === 1} onclick={() => removeColumn(c)}><X size={14} aria-hidden="true" /></button>
              </span>
            </th>
          {/each}
          <th><button class="mini" type="button" aria-label="Add a column" onclick={addColumn}><Plus size={14} aria-hidden="true" /></button></th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row, r (r)}
          <tr>
            <td class:dup={duplicates.has(row.key.trim())}><input class="input mono" aria-label="Row {r + 1}: key" bind:value={row.key} maxlength="200" /></td>
            {#each value.columns as _column, c (c)}
              <td><input class="input" aria-label="Row {r + 1}: {value.columns[c]}" bind:value={row.cells[c]} maxlength="2000" /></td>
            {/each}
            <td><button class="mini" type="button" aria-label="Remove row {r + 1}" onclick={() => rows.splice(r, 1)}><X size={14} aria-hidden="true" /></button></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if duplicates.size}<p class="small error">Two rows have the key {[...duplicates][0]}: only the last one counts.</p>{/if}
  <button class="link-button small add" type="button" onclick={() => rows.push({ key: "", cells: value.columns.map(() => "") })}><Plus size={14} aria-hidden="true" /> Add a row</button>
</div>

<style>
  .table-editor {
    display: grid;
    gap: var(--space-2);
  }
  .grid-wrap {
    max-height: 360px;
    overflow: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th,
  td {
    padding: 2px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .head .input {
    font-weight: 600;
  }
  .dup .input {
    border-color: var(--critical-text);
  }
  .mini {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .mini:disabled {
    opacity: 0.35;
  }
  .add {
    justify-self: start;
  }
  .error {
    margin: 0;
    color: var(--critical-text);
  }
</style>
