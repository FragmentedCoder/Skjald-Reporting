<script lang="ts">
  import type { NameEntry } from "#lib/templates/catalogue.js";
  import TypeCode from "./TypeCode.svelte";

  // The names matching what's typed after "{{", under the field typed in. The field
  // keeps the focus: the arrow keys move through these, Enter or Tab picks one. A
  // popover, so a narrow field or the scrolling panel around it never cuts it off: as
  // wide as the names and descriptions need, under its field, and following it.
  let { id, options, active, anchor, onpick }: {
    id: string;
    options: NameEntry[];
    active: number;
    /** What it opens under: the field. */
    anchor: HTMLElement | undefined;
    onpick: (entry: NameEntry) => void;
  } = $props();

  let list = $state<HTMLUListElement>();

  function place() {
    if (!list || !anchor) return;
    const box = anchor.getBoundingClientRect();
    list.style.minWidth = `${Math.min(box.width, window.innerWidth - 16)}px`;
    const width = list.offsetWidth;
    const height = list.offsetHeight;
    const below = box.bottom + 4 + height <= window.innerHeight;
    list.style.top = `${below ? box.bottom + 4 : Math.max(box.top - 4 - height, 8)}px`;
    list.style.left = `${Math.max(Math.min(box.left, window.innerWidth - width - 8), 8)}px`;
  }

  $effect(() => {
    if (!list) return;
    list.showPopover();
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  });

  $effect(() => {
    void options.length;
    place();
  });

  $effect(() => {
    list?.querySelector(`#${CSS.escape(`${id}-${active}`)}`)?.scrollIntoView({ block: "nearest" });
  });
</script>

<!-- Pressing an option leaves the focus, and the caret, in the field. -->
<ul class="names" {id} role="listbox" aria-label="Names" popover="manual" bind:this={list} onmousedown={(e) => e.preventDefault()}>
  {#each options as entry, i (entry.name)}
    <!-- The keyboard works in the field (a combobox), so an option only needs the click. -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <li id="{id}-{i}" role="option" aria-selected={i === active} class:active={i === active} onclick={() => onpick(entry)}>
      <span class="label">{#if entry.field}<TypeCode type={entry.field} /> {/if}{entry.label}</span>
      <span class="name">{entry.name}</span>
    </li>
  {/each}
</ul>

<style>
  .names {
    position: fixed;
    inset: auto;
    width: max-content;
    max-width: min(440px, calc(100vw - 16px));
    max-height: 280px;
    margin: 0;
    padding: 4px;
    overflow-y: auto;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--text);
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
    font-size: 13px;
  }
  .name {
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
</style>
