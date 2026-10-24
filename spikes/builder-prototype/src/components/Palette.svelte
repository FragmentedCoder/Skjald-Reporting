<script>
  // A palette you drag copies out of (svelte-dnd-action's copy-on-drag pattern).
  // Clicking an entry adds it too, for touch screens and keyboard users.
  import {dndzone, TRIGGERS, SHADOW_ITEM_MARKER_PROPERTY_NAME} from 'svelte-dnd-action'

  let {entries, type, title, onadd} = $props()
  // The palette's entries are fixed for its lifetime, so reading them once is intended.
  // svelte-ignore state_referenced_locally
  let items = $state.raw(entries.map((e) => ({...e, palette: true})))
  let ignoring = false

  function consider(e) {
    const {trigger, id} = e.detail.info
    if (trigger === TRIGGERS.DRAG_STARTED) {
      const index = items.findIndex((i) => i.id === id)
      const next = e.detail.items.filter((i) => !i[SHADOW_ITEM_MARKER_PROPERTY_NAME])
      next.splice(index, 0, {...items[index], id: `${items[index].kind}-${Math.random().toString(36).slice(2, 8)}`})
      items = next
      ignoring = true
    } else if (!ignoring) {
      items = e.detail.items
    } else {
      items = [...items]
    }
  }

  function finalize(e) {
    if (!ignoring) items = e.detail.items
    else items = [...items]
    ignoring = false
  }
</script>

<section class="palette panel" aria-label={title}>
  <div class="panel-head"><h2>{title}</h2></div>
  <p class="how">Drag onto the page, or click to add after the selected item.</p>
  <ul
    use:dndzone={{items, type, dropFromOthersDisabled: true, flipDurationMs: 120, dropTargetStyle: {}}}
    onconsider={consider}
    onfinalize={finalize}
  >
    {#each items as item (item.id)}
      <li>
        <button type="button" class="entry" onclick={() => onadd(item.kind)}>
          <span class="entry-in">
            <span class="glyph" aria-hidden="true">{item.glyph}</span>
            <span class="text"><span class="name">{item.label}</span><span class="hint">{item.hint}</span></span>
          </span>
        </button>
      </li>
    {/each}
  </ul>
</section>

<style>
  .palette { align-self: start; position: sticky; top: 12px; }
  .how { margin: 0; padding: 0 16px 10px; font-size: 12px; color: var(--text-muted); }
  ul { list-style: none; margin: 0; padding: 0 10px 12px; display: grid; gap: 4px; }
  .entry { width: 100%; display: block; padding: 0; border: 1px solid transparent;
    border-radius: var(--radius-md); background: transparent; text-align: left; cursor: grab; }
  /* svelte-dnd-action won't start a drag when the pressed element has a value (as buttons do), so this span takes the press. */
  .entry-in { display: flex; align-items: center; gap: 10px; padding: 7px 8px; border-radius: inherit; }
  .entry:hover { background: var(--surface-subtle); border-color: var(--border); }
  .glyph { flex: none; width: 30px; height: 30px; display: grid; place-items: center; border-radius: var(--radius-sm);
    background: var(--surface-subtle); color: var(--text); font-family: var(--font-mono); font-size: 12px; font-weight: 500; }
  .text { display: grid; min-width: 0; }
  .name { font-weight: 600; font-size: 13px; }
  .hint { font-size: 12px; color: var(--text-muted); }
  @media (max-width: 860px) {
    .palette { position: static; }
    ul { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
  }
</style>
