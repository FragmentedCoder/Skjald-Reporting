<script lang="ts">
  import { dndzone, type DndEvent } from "svelte-dnd-action";
  import { BLOCK_TYPES, blockSummary, newBlock } from "#lib/templates/blocks.js";
  import type { Block, BlockKind } from "#lib/templates/types.js";
  import BlockList from "./BlockList.svelte";
  import type { Dragged } from "./Palette.svelte";

  // The layout's blocks as an outline, in the order they print: sections and columns
  // hold blocks of their own, and blocks drag between them.
  let { blocks = $bindable(), depth = 0, label, selected, hidden, problems, readonly, onselect }: {
    blocks: Block[];
    depth?: number;
    label: string;
    selected: string | null;
    /** Blocks the sample answers leave out, and why. */
    hidden: Map<string, string>;
    problems: (id: string) => number;
    readonly: boolean;
    onselect: (id: string) => void;
  } = $props();

  type Item = Block | Dragged;

  function consider(event: CustomEvent<DndEvent<Item>>) {
    blocks = event.detail.items as Block[];
  }

  function finalize(event: CustomEvent<DndEvent<Item>>) {
    let added: Block | null = null;
    blocks = event.detail.items.map((item) => {
      if ("palette" in item) {
        added = newBlock(item.kind as BlockKind, depth > 0);
        return added;
      }
      return item;
    });
    if (added) onselect((added as Block).id);
  }
</script>

<ol class="blocks" class:nested={depth > 0} aria-label={label}
  use:dndzone={{ items: blocks, type: "blocks", flipDurationMs: 150, dragDisabled: readonly,
                 dropTargetStyle: { outline: "2px dashed var(--link)", outlineOffset: "2px" } }}
  onconsider={consider} onfinalize={finalize}>
  {#each blocks as b (b.id)}
    {#if "palette" in b}
      <li class="block shadow">{(b as unknown as Dragged).label}</li>
    {:else}
      {@const type = BLOCK_TYPES[b.kind]}
      {@const flagged = problems(b.id)}
      {@const why = hidden.get(b.id)}
      <li class="block kind-{b.kind}" class:selected={selected === b.id} class:hidden={why}>
        <button class="pick" type="button" onclick={() => onselect(b.id)} aria-label="{type.label}: {blockSummary(b)}, edit">
          <span class="pick-in">
            <span class="icon" aria-hidden="true"><type.icon size={15} aria-hidden="true" /></span>
            <span class="body">
              <span class="label">{blockSummary(b)}</span>
              <span class="meta small">{type.label}{#if b.visible_when} · printed when a rule says so{/if}{#if b.kind === "section" && b.repeat_for} · once for each row{/if}{#if b.kind === "section" && b.new_page} · new page{/if}</span>
            </span>
            {#if why}<span class="note small">{why}</span>{/if}
            {#if flagged}<span class="flag small">{flagged} problem{flagged === 1 ? "" : "s"}</span>{/if}
          </span>
        </button>
        {#if b.kind === "section"}
          <div class="inside">
            <BlockList bind:blocks={b.blocks} depth={depth + 1} label="Blocks in “{b.title}”" {selected} {hidden} {problems} {readonly} {onselect} />
            {#if !b.blocks.length}<p class="empty small muted">Drag blocks into this section.</p>{/if}
          </div>
        {:else if b.kind === "columns"}
          <div class="columns">
            {#each b.columns as _column, c (c)}
              <div class="column">
                <BlockList bind:blocks={b.columns[c]} depth={depth + 1} label="Column {c + 1}" {selected} {hidden} {problems} {readonly} {onselect} />
              </div>
            {/each}
          </div>
        {/if}
      </li>
    {/if}
  {/each}
</ol>

<style>
  .blocks {
    display: grid;
    gap: var(--space-1);
    min-height: 40px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .block {
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--surface);
  }
  .block.kind-section {
    background: var(--bg);
  }
  .block.selected {
    border-color: var(--link);
    box-shadow: 0 0 0 1px var(--link);
  }
  .block.hidden .label {
    color: var(--text-muted);
  }
  .shadow {
    padding: var(--space-2) var(--space-3);
    border-style: dashed;
    color: var(--text-muted);
  }
  .pick {
    display: block;
    width: 100%;
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    text-align: left;
    cursor: grab;
  }
  .pick-in {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 6px var(--space-2);
  }
  .icon {
    display: grid;
    flex: none;
    place-items: center;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    background: var(--surface-subtle);
  }
  .body {
    display: grid;
    flex: 1;
    min-width: 0;
  }
  .label {
    overflow: hidden;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .kind-section > .pick .label {
    font-family: var(--font-display);
    font-size: 17px;
    font-weight: 400;
  }
  .meta,
  .note {
    color: var(--text-muted);
  }
  .note {
    max-width: 40%;
    text-align: right;
  }
  .flag {
    padding: 0 8px;
    border-radius: var(--radius-pill);
    background: var(--warning-bg);
    color: var(--warning-text);
    font-weight: 600;
    white-space: nowrap;
  }
  .inside {
    padding: 0 var(--space-2) var(--space-2) var(--space-6);
  }
  .columns {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: var(--space-2);
    padding: 0 var(--space-2) var(--space-2);
  }
  .column {
    padding: var(--space-1);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-md);
  }
  .empty {
    margin: 0;
    padding: var(--space-2);
    text-align: center;
  }
</style>
