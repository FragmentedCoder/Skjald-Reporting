<script lang="ts">
  import type { NameEntry } from "#lib/templates/catalogue.js";

  // The names matching what's typed after "{{", under the field typed in. The field
  // keeps the focus: the arrow keys move through these, Enter or Tab picks one.
  let { id, options, active, onpick }: {
    id: string;
    options: NameEntry[];
    active: number;
    onpick: (entry: NameEntry) => void;
  } = $props();

  let list = $state<HTMLUListElement>();

  $effect(() => {
    list?.querySelector(`#${CSS.escape(`${id}-${active}`)}`)?.scrollIntoView({ block: "nearest" });
  });
</script>

<!-- Pressing an option leaves the focus, and the caret, in the field. -->
<ul class="names" {id} role="listbox" aria-label="Names" bind:this={list} onmousedown={(e) => e.preventDefault()}>
  {#each options as entry, i (entry.name)}
    <!-- The keyboard works in the field (a combobox), so an option only needs the click. -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <li id="{id}-{i}" role="option" aria-selected={i === active} class:active={i === active} onclick={() => onpick(entry)}>
      <span class="label">{entry.label}</span>
      <span class="name">{entry.name}</span>
    </li>
  {/each}
</ul>

<style>
  .names {
    position: absolute;
    z-index: 20;
    top: calc(100% + 4px);
    right: 0;
    left: 0;
    max-height: 240px;
    margin: 0;
    padding: 4px;
    overflow-y: auto;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface);
    box-shadow: 0 8px 24px rgb(15 27 45 / 0.16);
    list-style: none;
  }
  li {
    display: grid;
    padding: 4px 8px;
    border-radius: 6px;
    cursor: pointer;
  }
  li.active,
  li:hover {
    background: var(--surface-subtle);
  }
  .label {
    overflow: hidden;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name {
    overflow: hidden;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 12px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
