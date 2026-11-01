<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import Archive from "@lucide/svelte/icons/archive";
  import ArchiveRestore from "@lucide/svelte/icons/archive-restore";
  import Copy from "@lucide/svelte/icons/copy";
  import Download from "@lucide/svelte/icons/download";
  import Languages from "@lucide/svelte/icons/languages";
  import Upload from "@lucide/svelte/icons/upload";
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import { onDestroy, onMount } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import TemplateCover from "#lib/components/TemplateCover.svelte";
  import RowMenu, { type MenuItem } from "#lib/components/RowMenu.svelte";
  import { dateTime } from "#lib/format.js";
  import { PreviewStyle } from "#lib/reportStyles/preview.svelte.js";
  import { templatesApi, type TemplateSummary } from "#lib/templates/api.js";
  import { Covers } from "#lib/templates/covers.js";
  import { toast } from "#lib/toast.svelte.js";

  // Every template, for those who build them, as cards: its first page, name and
  // description, what's published and what's in a draft, and when it was made.
  let templates = $state<TemplateSummary[] | null>(null);
  let error = $state<string | null>(null);

  let adding = $state(false);
  let name = $state("");
  let description = $state("");
  let busy = $state(false);

  let copying = $state<TemplateSummary | null>(null);
  let copyOpen = $state(false);
  let copyName = $state("");
  // For a translation: the copy's report language; null for a plain copy.
  let copyLanguage = $state<"da" | "en" | null>(null);
  let deleting = $state<TemplateSummary | null>(null);
  let deleteOpen = $state(false);

  async function load() {
    try {
      templates = await templatesApi.list();
      error = null;
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The templates could not be loaded.";
    }
  }

  async function create(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    try {
      const created = await templatesApi.create(name.trim(), description.trim());
      adding = false;
      await goto(resolve("/(app)/templates/[id]", { id: String(created.id) }));
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The template could not be created.", "critical");
    } finally {
      busy = false;
    }
  }

  async function copy(event: SubmitEvent) {
    event.preventDefault();
    if (!copying) return;
    busy = true;
    try {
      const created = await templatesApi.copy(copying.id, copyName.trim(), copyLanguage);
      copyOpen = false;
      if (copyLanguage) {
        toast(`“${created.name}” is a new template: change its text on the Strings tab.`, "ok");
        await goto(resolve("/(app)/templates/[id]/strings", { id: String(created.id) }));
      } else {
        toast(`“${created.name}” is a new template, as a draft.`, "ok");
        await load();
      }
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The template could not be copied.", "critical");
    } finally {
      busy = false;
    }
  }

  // A .skjald file from another install (or this one): a new template, as a draft.
  let importing = $state(false);
  async function importFile(event: Event & { currentTarget: HTMLInputElement }) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    importing = true;
    try {
      const done = await templatesApi.importFile(file);
      const extra = [
        done.library_added.length ? `added to the library: ${done.library_added.join(", ")}` : "",
        done.library_kept.length ? `already in the library, left as they were: ${done.library_kept.join(", ")}` : "",
        done.style_added ? `added the style ${done.style_added}` : "",
      ].filter(Boolean);
      toast(`“${done.template.name}” is imported as a draft${extra.length ? `; ${extra.join("; ")}` : ""}.`, "ok");
      await goto(resolve("/(app)/templates/[id]", { id: String(done.template.id) }));
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The file couldn't be imported.", "critical");
    } finally {
      importing = false;
    }
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

  function menu(t: TemplateSummary): MenuItem[] {
    const items: MenuItem[] = [
      { label: "Copy", icon: Copy, run: () => { copying = t; copyName = `${t.name} (copy)`; copyLanguage = null; copyOpen = true; } },
      { label: "Copy for translation", icon: Languages, run: () => { copying = t; copyName = `${t.name} (translation)`; copyLanguage = "da"; copyOpen = true; } },
      { label: "Export", icon: Download, run: () => { window.location.assign(templatesApi.exportUrl(t.id)); } },
    ];
    if (t.retired) items.push({ label: "Bring back", icon: ArchiveRestore, run: () => act(() => templatesApi.restore(t.id), `“${t.name}” can be used again.`) });
    else if (t.latest_version !== null) items.push({ label: "Retire", icon: Archive, run: () => act(() => templatesApi.retire(t.id), `“${t.name}” is retired: no new reports use it.`) });
    if (t.latest_version === null) items.push({ label: "Delete", icon: X, danger: true, run: () => { deleting = t; deleteOpen = true; } });
    return items;
  }

  // The cards' first pages: drawn in the company's default style, one by one.
  const covers = new Covers();
  const looks = new PreviewStyle();
  onMount(() => {
    void load();
    void looks.load();
  });
  onDestroy(() => covers.close());
</script>

<svelte:head><title>{pageTitle("Templates")}</title></svelte:head>

<main class="page-content">
  <div class="page-header">
    <div>
      <h1 class="title">Templates</h1>
      <p class="small muted">
        What each kind of report asks the technician, how its PDF is laid out, and its rules.
        Reports use published versions, which never change.
      </p>
    </div>
    <div class="button-row">
      <label class="button button-secondary" class:disabled={importing}>
        <Upload size={18} aria-hidden="true" /> {importing ? "Importing…" : "Import"}
        <input type="file" class="visually-hidden" accept=".skjald,application/zip" disabled={importing} onchange={importFile} />
      </label>
      <button class="button button-primary" type="button" onclick={() => { adding = true; name = ""; description = ""; }}>
        <Plus size={18} aria-hidden="true" />
        New template
      </button>
    </div>
  </div>

  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

  {#if templates}
    {#if templates.length}
      <ul class="cards" aria-label="Templates">
        {#each templates as t (t.id)}
          {@const href = resolve("/(app)/templates/[id]", { id: String(t.id) })}
          <li class="card" class:retired={t.retired}>
            <a class="picture" {href} tabindex="-1" aria-hidden="true"><TemplateCover template={t} {covers} {looks} /></a>
            <div class="about">
              <div class="title-row">
                <a class="name" {href}>{t.name}</a>
                <RowMenu label="Actions for {t.name}" items={menu(t)} />
              </div>
              {#if t.description}<p class="small muted description" title={t.description}>{t.description}</p>{/if}
              <div class="status">
                {#if t.retired}<Pill tone="neutral" text="Retired" />{/if}
                {#if t.latest_version !== null}
                  <Pill tone="ok" text="Version {t.latest_version}" />
                {:else}
                  <Pill tone="neutral" text="Not published yet" />
                {/if}
                {#if t.draft}<Pill tone="info" text={t.latest_version !== null ? "Draft changes" : "Draft"} />{/if}
              </div>
              <p class="small muted when">
                {#if t.latest_version !== null}Published {dateTime(t.published_at ?? "")}<br />{/if}
                Created {dateTime(t.created_at)}{t.created_by ? ` by ${t.created_by}` : ""}
              </p>
            </div>
          </li>
        {/each}
      </ul>
    {:else}
      <section class="empty">
        <p>No templates yet.</p>
        <p class="small muted">Make the first one: its questions, its PDF and its rules, then publish it for technicians.</p>
      </section>
    {/if}
  {/if}
</main>

<Dialog bind:open={adding} title="New template">
  <form id="new-template" class="stack" onsubmit={create}>
    <div class="field">
      <label for="template-name">Name</label>
      <input id="template-name" class="input" bind:value={name} required maxlength="200" placeholder="Security incident report" />
    </div>
    <div class="field">
      <label for="template-description">Description <span class="muted">(optional)</span></label>
      <textarea id="template-description" class="input" rows="2" bind:value={description} maxlength="1000"></textarea>
      <span class="hint">For other designers. Technicians see the name.</span>
    </div>
  </form>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (adding = false)}>Cancel</button>
    <button class="button button-primary" type="submit" form="new-template" disabled={busy || !name.trim()}>Create</button>
  {/snippet}
</Dialog>

<Dialog bind:open={copyOpen} title={copyLanguage ? "Copy for translation" : "Copy template"}>
  <form id="copy-template" class="stack" onsubmit={copy}>
    <p class="small muted">The copy starts as a draft of its own, from {copying?.draft ? "the draft" : "the newest version"}, images included.{copyLanguage ? " Its text is changed on the Strings tab, where every piece of it is on one page." : ""}</p>
    <div class="field">
      <label for="copy-name">Name of the copy</label>
      <input id="copy-name" class="input" bind:value={copyName} required maxlength="200" />
    </div>
    {#if copyLanguage}
      <div class="field">
        <label for="copy-language">Report language</label>
        <select id="copy-language" class="input short" bind:value={copyLanguage}>
          <option value="da">Danish</option>
          <option value="en">English</option>
        </select>
        <span class="hint">Dates and numbers in the PDF follow it.</span>
      </div>
    {/if}
  </form>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (copyOpen = false)}>Cancel</button>
    <button class="button button-primary" type="submit" form="copy-template" disabled={busy || !copyName.trim()}>Copy</button>
  {/snippet}
</Dialog>

<Dialog bind:open={deleteOpen} title="Delete template">
  <p>Delete “{deleting?.name}”? It was never published, so no report uses it. This can't be undone.</p>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (deleteOpen = false)}>Cancel</button>
    <button class="button button-primary danger-fill" type="button" onclick={() => {
      const t = deleting;
      deleteOpen = false;
      if (t) void act(() => templatesApi.remove(t.id), `“${t.name}” is deleted.`);
    }}>Delete</button>
  {/snippet}
</Dialog>

<style>
  .short {
    max-width: 12rem;
  }
  .disabled {
    opacity: 0.6;
    pointer-events: none;
  }
  /* Cards, as many to a row as fit. */
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .card {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .card:hover {
    border-color: var(--border-strong);
  }
  .card:focus-within {
    outline: 2px solid var(--link);
    outline-offset: 2px;
  }
  /* The top of the first page: what tells templates apart. */
  .picture {
    display: block;
    aspect-ratio: 4 / 3;
    overflow: hidden;
    border-bottom: 1px solid var(--border);
    background: var(--surface-subtle);
  }
  .about {
    display: grid;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4) var(--space-4);
  }
  .title-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .name {
    color: var(--text);
    font-weight: 600;
    text-decoration: none;
  }
  .name:hover {
    text-decoration: underline;
  }
  .description {
    display: -webkit-box;
    margin: 0;
    overflow: hidden;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .status {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
  }
  .when {
    margin: 0;
  }
  .retired .picture {
    opacity: 0.5;
  }
  .retired .name {
    color: var(--text-muted);
  }
  .danger-fill {
    background: var(--critical-text);
    color: var(--surface);
  }
  .empty {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-8);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    text-align: center;
  }
</style>
