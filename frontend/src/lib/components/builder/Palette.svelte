<script lang="ts" module>
  import type { Icon } from "#lib/templates/fields.js";

  export interface PaletteEntry {
    kind: string;
    label: string;
    hint: string;
    icon: Icon;
    group: string;
  }

  /** What a palette entry looks like while it's dragged into a list. */
  export interface Dragged extends PaletteEntry {
    id: string;
    palette: true;
  }
</script>

<script lang="ts">
  import PaletteZone from "./PaletteZone.svelte";

  // A palette to drag copies out of, into a list of the same zone type; clicking an
  // entry adds it too, for touch screens and keyboard users, after whatever is
  // selected. Each group of entries is a zone of its own.
  let { entries, type, title, onadd }: {
    entries: PaletteEntry[];
    type: string;
    title: string;
    onadd: (kind: string) => void;
  } = $props();

  const groups = $derived([...new Set(entries.map((e) => e.group))]);
</script>

<section class="palette" aria-label={title}>
  <h2 class="palette-title">{title}</h2>
  <p class="how small muted">Drag into place, or click to add after what's selected.</p>
  {#each groups as group (group)}
    {#if groups.length > 1}<h3 class="group">{group}</h3>{/if}
    <PaletteZone entries={entries.filter((e) => e.group === group)} {type} {onadd} />
  {/each}
</section>

<style>
  .palette {
    position: sticky;
    top: var(--space-4);
    align-self: start;
    max-height: calc(100vh - 2 * var(--space-4));
    overflow-y: auto;
    padding: var(--space-3);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .palette-title {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }
  .how {
    margin: var(--space-1) 0 var(--space-2);
  }
  .group {
    margin: var(--space-3) 0 var(--space-1);
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  @media (max-width: 1100px) {
    .palette {
      position: static;
      max-height: none;
    }
  }
</style>
