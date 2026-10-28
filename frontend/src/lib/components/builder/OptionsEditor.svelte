<script lang="ts">
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import { freeKey, keyFrom } from "#lib/templates/edit.js";

  // The choices of a dropdown or multi-select: what the technician sees (the label)
  // and what rules compare (the value, made from the label until it's changed).
  let { options = $bindable(), id }: { options: { value: string; label: string }[]; id: string } = $props();

  function add() {
    const label = `Option ${options.length + 1}`;
    options.push({ label, value: freeKey(keyFrom(label), options.map((o) => o.value)) });
  }

  function move(index: number, by: number) {
    const [option] = options.splice(index, 1);
    options.splice(index + by, 0, option);
  }
</script>

<fieldset class="options">
  <legend>Choices</legend>
  <div class="grid">
    <span class="small muted">Shown as</span><span class="small muted">Value in rules</span><span></span>
    {#each options as option, index (index)}
      <input class="input" aria-label="Choice {index + 1}" bind:value={option.label} maxlength="200" />
      <input class="input mono" aria-label="Value of choice {index + 1}" bind:value={option.value} maxlength="200" />
      <span class="row-actions">
        <button class="mini" type="button" aria-label="Move choice {index + 1} up" disabled={index === 0} onclick={() => move(index, -1)}><ArrowUp size={14} aria-hidden="true" /></button>
        <button class="mini" type="button" aria-label="Move choice {index + 1} down" disabled={index === options.length - 1} onclick={() => move(index, 1)}><ArrowDown size={14} aria-hidden="true" /></button>
        <button class="mini" type="button" aria-label="Remove choice {index + 1}" disabled={options.length === 1} onclick={() => options.splice(index, 1)}><X size={14} aria-hidden="true" /></button>
      </span>
    {/each}
  </div>
  <button class="button button-secondary small-button" type="button" onclick={add} id="{id}-add"><Plus size={16} aria-hidden="true" /> Add a choice</button>
</fieldset>

<style>
  .options {
    margin: 0;
    padding: 0;
    border: 0;
  }
  legend {
    margin-bottom: var(--space-1);
    font-size: 14px;
    font-weight: 600;
  }
  .grid {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) auto;
    gap: var(--space-1) var(--space-2);
    align-items: center;
    margin-bottom: var(--space-2);
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
    padding: 4px 10px;
    font-size: 13px;
  }
</style>
