<script lang="ts">
  import History from "@lucide/svelte/icons/history";
  import Lock from "@lucide/svelte/icons/lock";
  import LockOpen from "@lucide/svelte/icons/lock-open";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Plus from "@lucide/svelte/icons/plus";
  import Upload from "@lucide/svelte/icons/upload";
  import X from "@lucide/svelte/icons/x";
  import { onMount } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import TableEditor from "#lib/components/library/TableEditor.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import RowMenu, { type MenuItem } from "#lib/components/RowMenu.svelte";
  import { dateTime } from "#lib/format.js";
  import { entryName, libraryApi, type LibraryEntry, type LibraryKind, type LibraryValue, type LibraryVersion, type TableValue } from "#lib/library.js";
  import { can, session } from "#lib/session.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  // The shared library: variables, text snippets and data tables every template and
  // report can use. Every change is kept, and administrators can lock an entry.
  const KINDS: { kind: LibraryKind; label: string; one: string; about: string }[] = [
    { kind: "variable", label: "Variables", one: "variable", about: "One line each, such as the service desk's phone number. Templates read them as vars.name." },
    { kind: "snippet", label: "Text snippets", one: "text snippet", about: "Paragraphs to reuse, which may use variables in {{ }}. Templates read them as text.name; technicians can insert them in long answers." },
    { kind: "table", label: "Data tables", one: "data table", about: "Values by key, such as a severity for each CVSS rating. Templates read them with lookup(\"table\", key), or lookup(\"table\", key, \"column\")." },
  ];

  let entries = $state<LibraryEntry[] | null>(null);
  let error = $state<string | null>(null);
  let shown = $state<LibraryKind>("variable");
  const locks = $derived(can(session.current, "lock_library_entries"));
  const kind = $derived(KINDS.find((k) => k.kind === shown) ?? KINDS[0]);

  async function load() {
    try {
      entries = await libraryApi.list();
      error = null;
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The library could not be loaded.";
    }
  }
  onMount(load);

  // Adding or changing one
  let editing = $state(false);
  let current = $state<LibraryEntry | null>(null);
  let key = $state("");
  let description = $state("");
  let value = $state<LibraryValue>({ value: "" });
  let busy = $state(false);

  function blank(k: LibraryKind): LibraryValue {
    if (k === "variable") return { value: "" };
    if (k === "snippet") return { text: "" };
    return { key_label: "Key", columns: ["Value"], rows: {} };
  }

  function open(entry: LibraryEntry | null) {
    current = entry;
    key = entry?.key ?? "";
    description = entry?.description ?? "";
    value = entry ? structuredClone($state.snapshot(entry.value) as LibraryValue) : blank(shown);
    editing = true;
  }

  async function save(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    try {
      const snapshot = $state.snapshot(value) as LibraryValue;
      if (current) await libraryApi.update(current.id, current.version, description, snapshot);
      else await libraryApi.create(shown, key, description, snapshot);
      editing = false;
      toast(current ? `${entryName(current)} is changed.` : `${entryName({ kind: shown, key })} is in the library.`, "ok");
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The entry could not be saved.", "critical");
    } finally {
      busy = false;
    }
  }

  async function importFile(entry: LibraryEntry, event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    try {
      const updated = await libraryApi.importTable(entry.id, file);
      toast(`${Object.keys((updated.value as TableValue).rows).length} rows imported into ${entry.key}.`, "ok");
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The file could not be imported.", "critical");
    }
  }

  // History
  let history = $state<LibraryVersion[] | null>(null);
  let historyOf = $state<LibraryEntry | null>(null);
  let showingHistory = $state(false);
  async function showHistory(entry: LibraryEntry) {
    historyOf = entry;
    history = null;
    showingHistory = true;
    history = await libraryApi.versions(entry.id);
  }

  async function act(run: () => Promise<unknown>, done: string) {
    try {
      await run();
      toast(done, "ok");
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "That didn't work. Try again.", "critical");
    }
  }

  function menu(entry: LibraryEntry): MenuItem[] {
    const items: MenuItem[] = [];
    if (!entry.locked) items.push({ label: "Change", icon: Pencil, run: () => open(entry) });
    items.push({ label: "History", icon: History, run: () => void showHistory(entry) });
    if (locks) {
      items.push(entry.locked
        ? { label: "Unlock", icon: LockOpen, run: () => void act(() => libraryApi.unlock(entry.id), `${entryName(entry)} can be changed again.`) }
        : { label: "Lock", icon: Lock, run: () => void act(() => libraryApi.lock(entry.id), `${entryName(entry)} is locked: nobody can change it.`) });
    }
    if (!entry.locked) items.push({ label: "Remove", icon: X, danger: true, run: () => void act(() => libraryApi.remove(entry.id), `${entryName(entry)} is removed. Its history is kept.`) });
    return items;
  }

  const summary = (entry: LibraryEntry) => {
    if (entry.kind === "variable") return (entry.value as { value: string }).value;
    if (entry.kind === "snippet") return (entry.value as { text: string }).text;
    const t = entry.value as TableValue;
    const n = Object.keys(t.rows).length;
    return `${n} row${n === 1 ? "" : "s"}: ${t.key_label} → ${t.columns.join(", ")}`;
  };
</script>

<svelte:head><title>{pageTitle("Library")}</title></svelte:head>

<main class="page-content">
  <div class="page-header">
    <div>
      <h1 class="title">Library</h1>
      <p class="small muted">Shared by every template and report. Every change is kept, and a report keeps the values it was signed with.</p>
    </div>
    <button class="button button-primary" type="button" onclick={() => open(null)}>
      <Plus size={18} aria-hidden="true" /> Add a {kind.one}
    </button>
  </div>

  <div class="kinds" role="group" aria-label="Show">
    {#each KINDS as k (k.kind)}
      <button type="button" aria-pressed={shown === k.kind} onclick={() => (shown = k.kind)}>
        {k.label} <span class="count">{entries?.filter((e) => e.kind === k.kind).length ?? ""}</span>
      </button>
    {/each}
  </div>
  <p class="small muted">{kind.about}</p>

  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

  {#if entries}
    {@const listed = entries.filter((e) => e.kind === shown)}
    {#if listed.length}
      <div class="section table-wrap">
        <table class="table">
          <thead><tr><th>Name</th><th>Value</th><th class="roomy">Changed</th><th><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>
            {#each listed as entry (entry.id)}
              <tr>
                <td>
                  <span class="mono">{entryName(entry)}</span>
                  {#if entry.locked}<Pill tone="warning" text="Locked" />{/if}
                  {#if entry.description}<span class="small muted block">{entry.description}</span>{/if}
                </td>
                <td class="value">{summary(entry)}</td>
                <td class="roomy small">{entry.updated_by ?? "Someone"}, {dateTime(entry.updated_at)}<span class="muted"> · version {entry.version}</span></td>
                <td class="actions">
                  {#if entry.kind === "table" && !entry.locked}
                    <label class="icon-label" title="Import rows from CSV or JSON">
                      <Upload size={16} aria-hidden="true" /><span class="visually-hidden">Import rows into {entry.key}</span>
                      <input type="file" accept=".csv,.json,text/csv,application/json" class="visually-hidden" onchange={(e) => importFile(entry, e)} />
                    </label>
                  {/if}
                  <RowMenu label="Actions for {entryName(entry)}" items={menu(entry)} />
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <section class="empty"><p>No {kind.label.toLowerCase()} yet.</p></section>
    {/if}
  {/if}
</main>

<Dialog bind:open={editing} title={current ? `Change ${entryName(current)}` : `Add a ${KINDS.find((k) => k.kind === shown)?.one}`}>
  <form id="library-entry" class="stack" onsubmit={save}>
    {#if !current}
      <div class="field">
        <label for="entry-key">Name</label>
        <input id="entry-key" class="input mono" bind:value={key} required maxlength="50" pattern="[a-z][a-z0-9_]*" placeholder="support_phone" />
        <span class="hint">Small letters, digits and _, starting with a letter. Templates read it as {entryName({ kind: shown, key: key || "name" })}.</span>
      </div>
    {/if}
    <div class="field">
      <label for="entry-description">What it is <span class="muted">(optional)</span></label>
      <input id="entry-description" class="input" bind:value={description} maxlength="500" />
    </div>
    {#if "value" in value}
      <div class="field"><label for="entry-value">Value</label><input id="entry-value" class="input" bind:value={value.value} maxlength="2000" /></div>
    {:else if "text" in value}
      <div class="field">
        <label for="entry-text">Text</label>
        <textarea id="entry-text" class="input" rows="6" bind:value={value.text} maxlength="20000"></textarea>
        <span class="hint">Variables can go in {"{{ }}"}, such as {"{{vars.support_phone}}"}; other snippets can't.</span>
      </div>
    {:else}
      <TableEditor bind:value={() => value as TableValue, (v) => (value = v)} />
    {/if}
  </form>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (editing = false)}>Cancel</button>
    <button class="button button-primary" type="submit" form="library-entry" disabled={busy}>Save</button>
  {/snippet}
</Dialog>

<Dialog bind:open={showingHistory} title="History of {historyOf ? entryName(historyOf) : ''}">
  {#if history}
    <ol class="history">
      {#each history as v (v.number)}
        <li><span class="small muted">Version {v.number} · {v.saved_by ?? "Someone"}, {dateTime(v.saved_at)}</span>
          <span class="value">{historyOf ? summary({ ...historyOf, value: v.value }) : ""}</span></li>
      {/each}
    </ol>
  {:else}
    <p class="muted">Loading…</p>
  {/if}
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (showingHistory = false)}>Close</button>
  {/snippet}
</Dialog>

<style>
  .kinds {
    display: inline-flex;
    padding: 2px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }
  .kinds button {
    padding: 4px 12px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--text-muted);
    font-weight: 600;
    cursor: pointer;
  }
  .kinds button[aria-pressed="true"] {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .count {
    color: var(--text-muted);
    font-weight: 400;
  }
  .block {
    display: block;
  }
  .value {
    max-width: 420px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .actions {
    width: 1%;
    white-space: nowrap;
  }
  .icon-label {
    display: inline-grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    vertical-align: middle;
  }
  .icon-label:hover {
    background: var(--surface-subtle);
  }
  .table-wrap {
    container-type: inline-size;
  }
  @container (max-width: 560px) {
    .roomy {
      display: none;
    }
  }
  .empty {
    padding: var(--space-8);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    text-align: center;
  }
  .history {
    display: grid;
    gap: var(--space-2);
    max-height: 360px;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
  }
  .history li {
    display: grid;
  }
</style>
