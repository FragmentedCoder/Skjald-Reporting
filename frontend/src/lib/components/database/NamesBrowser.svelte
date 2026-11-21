<script lang="ts">
  import Copy from "@lucide/svelte/icons/copy";
  import Search from "@lucide/svelte/icons/search";
  import TypeCode from "#lib/components/builder/TypeCode.svelte";
  import { searchNames, type NameGroup, type NameRow } from "#lib/templates/nameGroups.js";
  import { toast } from "#lib/toast.svelte.js";

  // The names a template can read, to look up: search them by any word, and see what
  // each is, its kind and an example, made-up ones set apart where some are current
  // values. On a page each name has a button to copy it in
  // {{ }}; in the editor's Names drawer (compact) a name is picked, to go where the
  // designer is typing.
  let { groups, compact = false, onpick, id = "names" }: {
    groups: NameGroup[];
    compact?: boolean;
    /** Given, clicking a name picks it, rather than copying it. */
    onpick?: (row: NameRow) => void;
    id?: string;
  } = $props();

  let query = $state("");
  const found = $derived(searchNames(groups, query));
  const count = $derived(found.reduce((n, g) => n + g.rows.length, 0));

  async function copy(row: NameRow) {
    const text = `{{${row.name}}}`;
    try {
      await navigator.clipboard.writeText(text);
      toast(`Copied ${text}: paste it where it should go.`, "ok");
    } catch {
      toast(`The browser didn't allow copying. Type ${text} instead.`, "warning");
    }
  }
</script>

<div class="browser" class:compact>
  <div class="search">
    <div class="search-box">
      <Search class="search-icon" size={16} aria-hidden="true" />
      <label class="visually-hidden" for="{id}-search">Search names</label>
      <input id="{id}-search" class="input" type="search" placeholder="Search, such as customer, date or phone" bind:value={query} autocomplete="off" />
    </div>
    <span class="small muted" aria-live="polite">{count} name{count === 1 ? "" : "s"}</span>
  </div>

  <div class="groups">
    {#each found as group (group.title)}
      <section class="section group" aria-label={group.title}>
        <h3 class="title">{group.title} <span class="count">{group.rows.length}</span></h3>
        {#if group.about}<p class="small muted about">{group.about}</p>{/if}
        {#if compact}
          <ul class="rows">
            {#each group.rows as row (row.name)}
              <li>
                <button type="button" class="row" onclick={() => (onpick ?? copy)(row)} title="Insert {`{{${row.name}}}`}">
                  <span class="line"><span class="mono name">{#if row.field}<TypeCode type={row.field} /> {/if}{row.name}</span><span class="kind small">{row.kind}</span></span>
                  <span class="small what">{row.what}</span>
                  <span class="small muted mono example" class:made-up={row.live === false}>{row.example}</span>
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>Name</th><th>What it is</th><th>Kind</th><th>Example</th></tr></thead>
              <tbody>
                {#each group.rows as row (row.name)}
                  <tr>
                    <td class="name-cell">
                      {#if row.field}<TypeCode type={row.field} />{/if}
                      <span class="mono name">{row.name}</span>
                      <button type="button" class="copy" onclick={() => (onpick ?? copy)(row)} aria-label="Copy {`{{${row.name}}}`}" title="Copy {`{{${row.name}}}`}">
                        <Copy size={14} aria-hidden="true" />
                      </button>
                    </td>
                    <td>{row.what}</td>
                    <td class="small">{row.kind}</td>
                    <td class="mono small example" class:made-up={row.live === false} title={row.live === false ? "Made up: there's nothing to show here yet" : undefined}>{row.example}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </section>
    {:else}
      <p class="muted">No names match “{query}”.</p>
    {/each}
  </div>
</div>

<style>
  .browser {
    display: grid;
    gap: var(--space-3);
  }
  .search {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    max-width: 640px;
    color: var(--text-muted);
  }
  .search-box {
    position: relative;
    flex: 1;
    min-width: 0;
  }
  .search-box :global(.search-icon) {
    position: absolute;
    top: 50%;
    left: 12px;
    color: var(--text-muted);
    transform: translateY(-50%);
    pointer-events: none;
  }
  .search-box .input {
    width: 100%;
    padding-left: 36px;
  }
  .search span {
    white-space: nowrap;
  }
  /* On a page the groups run in two columns where they fit; in the drawer, one. */
  .groups {
    columns: 2 560px;
    column-gap: var(--space-2);
  }
  .compact .groups {
    columns: auto;
  }
  .group {
    margin: 0 0 var(--space-2);
    break-inside: avoid;
  }
  .compact .group {
    padding: var(--space-3);
  }
  .title {
    margin: 0;
    font: var(--type-subheading);
  }
  .compact .title {
    font-size: 17px;
  }
  .count {
    padding: 0 8px;
    border-radius: var(--radius-pill);
    background: var(--surface-subtle);
    color: var(--text-muted);
    font: 600 12px/1.6 var(--font-sans);
    vertical-align: middle;
  }
  .about {
    margin: 0;
  }
  .name-cell {
    white-space: nowrap;
  }
  .name {
    overflow-wrap: anywhere;
  }
  .copy {
    display: inline-grid;
    place-items: center;
    width: 26px;
    height: 26px;
    margin-left: 4px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    vertical-align: middle;
    cursor: pointer;
  }
  .copy:hover,
  .copy:focus-visible {
    border-color: var(--border);
    color: var(--text);
  }
  .example {
    max-width: 260px;
    overflow-wrap: anywhere;
  }
  /* Where there's no current value to show: a made-up example, set apart. */
  .made-up {
    color: var(--text-muted);
    font-style: italic;
  }
  .rows {
    display: grid;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .row {
    display: grid;
    gap: 1px;
    width: 100%;
    padding: 6px 8px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: transparent;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }
  .row:hover,
  .row:focus-visible {
    border-color: var(--border);
    background: var(--surface-subtle);
  }
  .line {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .row .name {
    font-weight: 600;
  }
  .kind {
    flex: none;
    color: var(--text-muted);
  }
</style>
