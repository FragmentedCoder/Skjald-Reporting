<script lang="ts">
  import { dndzone, SHADOW_ITEM_MARKER_PROPERTY_NAME, type DndEvent } from "svelte-dnd-action";
  import { BLOCK_TYPES, blockSummary, newBlock } from "#lib/templates/blocks.js";
  import type { Block, BlockKind } from "#lib/templates/types.js";
  import BlockList from "./BlockList.svelte";
  import type { Dragged } from "./Palette.svelte";

  // The layout's blocks as an outline, in the order they print: sections and columns
  // hold blocks of their own, and blocks drag between them.
  let { blocks = $bindable(), depth = 0, label, empty, selected, hidden, problems, readonly, onselect }: {
    blocks: Block[];
    depth?: number;
    label: string;
    /** Shown in the list while it's empty, where a block can be dropped. */
    empty: string;
    selected: string | null;
    /** Blocks the sample answers leave out, and why. */
    hidden: Map<string, string>;
    problems: (id: string) => number;
    readonly: boolean;
    onselect: (id: string) => void;
  } = $props();

  type Item = Block | Dragged;

  // While something is dragged, the list shows the drag library's order, with its
  // placeholder in it; the template only changes once it's dropped, so a half-finished
  // move is never checked, previewed or saved.
  let dragging = $state.raw<Item[] | null>(null);
  const items = $derived(dragging ?? (blocks as Item[]));
  const placeholder = (item: Item) => "palette" in item || SHADOW_ITEM_MARKER_PROPERTY_NAME in item;

  // What kind of block it is, and what it does besides printing.
  function meta(b: Block): string {
    const section = b.kind === "section" ? b : null;
    return [
      section && depth > 0 ? "Subsection" : BLOCK_TYPES[b.kind].label,
      b.visible_when && "printed when a rule says so",
      section?.repeat_for && "once for each row",
      section?.new_page && "new page",
    ].filter(Boolean).join(" · ");
  }

  function consider(event: CustomEvent<DndEvent<Item>>) {
    dragging = event.detail.items;
  }

  function finalize(event: CustomEvent<DndEvent<Item>>) {
    let added: Block | null = null;
    dragging = null;
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

<ol class="blocks" class:nested={depth > 0} class:empty={!items.length} aria-label={label} data-empty={empty}
  use:dndzone={{ items, type: "blocks", flipDurationMs: 150, dragDisabled: readonly, centreDraggedOnCursor: true,
                 dropTargetClasses: ["dropping"], dropTargetStyle: {} }}
  onconsider={consider} onfinalize={finalize}>
  {#each items as b (b.id)}
    {#if placeholder(b)}
      <!-- Where it would land: one line, whatever it holds, so nothing drops into the block being moved. -->
      <li class="block shadow">{"palette" in b ? b.label : blockSummary(b)}</li>
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
              <span class="meta small">{meta(b)}</span>
            </span>
            {#if why}<span class="note small">{why}</span>{/if}
            {#if flagged}<span class="flag small">{flagged} problem{flagged === 1 ? "" : "s"}</span>{/if}
          </span>
        </button>
        {#if b.kind === "section"}
          <div class="inside">
            <BlockList bind:blocks={b.blocks} depth={depth + 1} label="Blocks in “{b.title}”" empty="Drag blocks into this section."
              {selected} {hidden} {problems} {readonly} {onselect} />
          </div>
        {:else if b.kind === "columns"}
          <div class="columns">
            {#each b.columns as _column, c (c)}
              <div class="column">
                <BlockList bind:blocks={b.columns[c]} depth={depth + 1} label="Column {c + 1}" empty="Drag blocks here."
                  {selected} {hidden} {problems} {readonly} {onselect} />
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
    border-radius: var(--radius-md);
    list-style: none;
  }
  /* Every list a block can be dropped into, while one is dragged. */
  .blocks:global(.dropping) {
    outline: 2px dashed var(--link);
    outline-offset: 2px;
  }
  /* An empty list says so where the block would land. */
  .blocks.empty::after {
    content: attr(data-empty);
    padding: var(--space-3);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-md);
    color: var(--text-muted);
    font-size: 13px;
    text-align: center;
  }
  /* The PDF's own list has room after its last block, for dropping one at the end. */
  .blocks:not(.nested) {
    position: relative;
  }
  .blocks:not(.nested):not(.empty):global(.dropping) {
    padding-bottom: var(--space-8);
  }
  .blocks:not(.nested):not(.empty):global(.dropping)::after {
    content: "Drop here to add it at the end.";
    position: absolute;
    right: 0;
    bottom: var(--space-3);
    left: 0;
    color: var(--text-muted);
    font-size: 13px;
    text-align: center;
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
</style>
