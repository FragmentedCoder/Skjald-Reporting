<script lang="ts">
  import { dndzone, SHADOW_ITEM_MARKER_PROPERTY_NAME, TRIGGERS, type DndEvent } from "svelte-dnd-action";
  import type { Dragged, PaletteEntry } from "./Palette.svelte";

  // One group of a palette: svelte-dnd-action's copy-on-drag pattern, so dragging an
  // entry out leaves a fresh copy behind.
  let { entries, type, onadd }: { entries: PaletteEntry[]; type: string; onadd: (kind: string) => void } = $props();

  const fresh = (entry: PaletteEntry): Dragged => ({ ...entry, id: `${entry.kind}-${Math.random().toString(36).slice(2, 10)}`, palette: true });
  // The entries are fixed for the palette's lifetime.
  // svelte-ignore state_referenced_locally
  let items = $state.raw<Dragged[]>(entries.map(fresh));
  let ignoring = false;

  function consider(event: CustomEvent<DndEvent<Dragged>>) {
    const { trigger, id } = event.detail.info;
    if (trigger === TRIGGERS.DRAG_STARTED) {
      const index = items.findIndex((i) => i.id === id);
      const next = event.detail.items.filter((i) => !(i as unknown as Record<string, unknown>)[SHADOW_ITEM_MARKER_PROPERTY_NAME]);
      next.splice(index, 0, fresh(items[index]));
      items = next;
      ignoring = true;
    } else if (!ignoring) {
      items = event.detail.items;
    } else {
      items = [...items];
    }
  }

  function finalize(event: CustomEvent<DndEvent<Dragged>>) {
    items = ignoring ? [...items] : event.detail.items;
    ignoring = false;
  }
</script>

<ul class="entries" use:dndzone={{ items, type, dropFromOthersDisabled: true, flipDurationMs: 120, centreDraggedOnCursor: true, dropTargetStyle: {} }}
  onconsider={consider} onfinalize={finalize}>
  {#each items as item (item.id)}
    <li>
      <button type="button" class="entry" onclick={() => onadd(item.kind)} title={item.hint}>
        <!-- svelte-dnd-action won't start a drag on an element with a value, as a button has, so this span takes the press. -->
        <span class="entry-in">
          <span class="icon" aria-hidden="true"><item.icon size={16} aria-hidden="true" /></span>
          <span class="text"><span class="name">{item.label}</span><span class="hint">{item.hint}</span></span>
        </span>
      </button>
    </li>
  {/each}
</ul>

<style>
  .entries {
    display: grid;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .entry {
    display: block;
    width: 100%;
    padding: 0;
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    background: transparent;
    color: inherit;
    text-align: left;
    cursor: grab;
  }
  .entry:hover,
  .entry:focus-visible {
    border-color: var(--border);
    background: var(--surface-subtle);
  }
  .entry-in {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 6px 8px;
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
  .text {
    display: grid;
    min-width: 0;
  }
  .name {
    font-size: 13px;
    font-weight: 600;
  }
  .hint {
    overflow: hidden;
    color: var(--text-muted);
    font-size: 12px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  @media (max-width: 1100px) {
    .entries {
      grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    }
  }
</style>
