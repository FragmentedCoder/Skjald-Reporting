<script lang="ts">
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import { freeKey, keyFrom } from "#lib/templates/edit.js";
  import { COLUMN_TYPES, FIELD_TYPES } from "#lib/templates/fields.js";
  import OptionsEditor from "./OptionsEditor.svelte";

  // The columns of a repeating group or a table. Each column has a variable name, as
  // a question has, which rules read from a row: row.ip, item.attempts.
  interface Column {
    key: string;
    label: string;
    type: string;
    required: boolean;
    settings: Record<string, unknown>;
  }

  type Option = { value: string; label: string };

  let { columns = $bindable(), id }: { columns: Column[]; id: string } = $props();

  function add() {
    const label = `Column ${columns.length + 1}`;
    columns.push({ key: freeKey(keyFrom(label), columns.map((c) => c.key)), label, type: "text", required: false, settings: FIELD_TYPES.text.settings() });
  }

  function retype(column: Column, type: string) {
    column.type = type;
    column.settings = FIELD_TYPES[type].settings();
  }

  function move(index: number, by: number) {
    const [column] = columns.splice(index, 1);
    columns.splice(index + by, 0, column);
  }
</script>

<fieldset class="columns">
  <legend>Columns</legend>
  {#each columns as column, index (index)}
    <div class="column">
      <div class="line">
        <input class="input" aria-label="Column {index + 1} heading" bind:value={column.label} maxlength="200" />
        <select class="input" aria-label="Column {index + 1} type" value={column.type} onchange={(e) => retype(column, e.currentTarget.value)}>
          {#each COLUMN_TYPES as type (type)}<option value={type}>{FIELD_TYPES[type].label}</option>{/each}
        </select>
        <span class="row-actions">
          <button class="mini" type="button" aria-label="Move column {index + 1} up" disabled={index === 0} onclick={() => move(index, -1)}><ArrowUp size={14} aria-hidden="true" /></button>
          <button class="mini" type="button" aria-label="Move column {index + 1} down" disabled={index === columns.length - 1} onclick={() => move(index, 1)}><ArrowDown size={14} aria-hidden="true" /></button>
          <button class="mini" type="button" aria-label="Remove column {index + 1}" disabled={columns.length === 1} onclick={() => columns.splice(index, 1)}><X size={14} aria-hidden="true" /></button>
        </span>
      </div>
      <div class="line details">
        <label class="small key">Name <input class="input mono" aria-label="Column {index + 1} variable name" bind:value={column.key} maxlength="50" pattern="[a-z][a-z0-9_]*" /></label>
        <label class="check small"><input type="checkbox" bind:checked={column.required} /> Required</label>
        {#if column.type === "number"}
          <label class="check small"><input type="checkbox" bind:checked={() => Boolean(column.settings.whole), (v) => (column.settings.whole = v)} /> Whole numbers</label>
        {/if}
      </div>
      {#if column.type === "dropdown"}
        <OptionsEditor bind:options={() => column.settings.options as Option[], (v) => (column.settings.options = v)} id="{id}-col-{index}" />
      {/if}
    </div>
  {/each}
  <button class="button button-secondary small-button" type="button" onclick={add}><Plus size={16} aria-hidden="true" /> Add a column</button>
</fieldset>

<style>
  .columns {
    display: grid;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    border: 0;
  }
  legend {
    margin-bottom: var(--space-1);
    font-size: 14px;
    font-weight: 600;
  }
  .column {
    display: grid;
    gap: var(--space-1);
    padding: var(--space-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
  }
  .line {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
  .line > .input:first-child {
    flex: 1 1 140px;
  }
  .line select {
    flex: 0 1 150px;
  }
  .key {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .key .input {
    width: 140px;
  }
  .row-actions {
    display: flex;
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
  .mini:hover:not(:disabled) {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .mini:disabled {
    opacity: 0.35;
    cursor: default;
  }
  .small-button {
    justify-self: start;
    padding: 4px 10px;
    font-size: 13px;
  }
</style>
