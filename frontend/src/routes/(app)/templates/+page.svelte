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
  import { can, session } from "#lib/session.svelte.js";
  import { withStepUp } from "#lib/stepUp.svelte.js";
  import { templatesApi, type TemplateSummary } from "#lib/templates/api.js";
  import { Covers } from "#lib/templates/covers.js";
  import { toast } from "#lib/toast.svelte.js";

  // Every template as a card: its first page, its language and name, who made it and
  // when, and a bar with its version and status. Those in use and those retired are on
  // tabs of their own. Designers open and change them; Administrators and Managers
  // can delete a retired one for good (Managers see the list for that only).
  let templates = $state<TemplateSummary[] | null>(null);
  let error = $state<string | null>(null);
  const builds = $derived(can(session.current, "build_templates"));
  const deletes = $derived(can(session.current, "delete_templates"));
  let showing = $state<"in-use" | "retired">("in-use");
  const inUse = $derived(templates?.filter((t) => !t.retired) ?? []);
  const retired = $derived(templates?.filter((t) => t.retired) ?? []);
  const shown = $derived(showing === "retired" ? retired : inUse);

  /** Where a template stands, for the bar at the bottom of its card. */
  function status(t: TemplateSummary): { tone: "ok" | "info" | "neutral" | "warning"; text: string } {
    if (t.retired) return { tone: "neutral", text: "Retired" };
    if (t.latest_version === null) return { tone: "info", text: "Draft" };
    if (t.draft) return { tone: "warning", text: "In use, draft changes" };
    return { tone: "ok", text: "In use" };
  }

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
  // A published template's name, typed to confirm deleting it for good.
  let deleteName = $state("");

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
    const items: MenuItem[] = [];
    if (builds) {
      items.push(
        { label: "Copy", icon: Copy, run: () => { copying = t; copyName = `${t.name} (copy)`; copyLanguage = null; copyOpen = true; } },
        { label: "Copy for translation", icon: Languages, run: () => { copying = t; copyName = `${t.name} (translation)`; copyLanguage = "da"; copyOpen = true; } },
        { label: "Export", icon: Download, run: () => { window.location.assign(templatesApi.exportUrl(t.id)); } },
      );
      if (t.retired) items.push({ label: "Bring back", icon: ArchiveRestore, run: () => act(() => templatesApi.restore(t.id), `“${t.name}” is in use again.`) });
      else if (t.latest_version !== null) items.push({ label: "Retire", icon: Archive, run: () => act(() => templatesApi.retire(t.id), `“${t.name}” is retired: no new reports use it. It's on the Retired tab.`) });
    }
    if ((builds && t.latest_version === null) || (deletes && t.retired)) {
      items.push({ label: "Delete", icon: X, danger: true, run: () => { deleting = t; deleteName = ""; deleteOpen = true; } });
    }
    return items;
  }

  async function remove() {
    const t = deleting;
    if (!t) return;
    busy = true;
    try {
      const published = t.latest_version !== null;
      await withStepUp(() => templatesApi.remove(t.id, published ? deleteName.trim() : undefined));
      deleteOpen = false;
      toast(`“${t.name}” is deleted.`, "ok");
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The template could not be deleted.", "critical");
    } finally {
      busy = false;
    }
  }

  // The cards' first pages: drawn in the company's default style, one by one.
  const covers = new Covers();
  const looks = new PreviewStyle();
  onMount(() => {
    void load();
    if (builds) void looks.load();
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
        A template starts as a draft; publishing it makes a version, which never changes, and new
        reports use the newest one. Changing a published template starts a new draft, and retiring
        it stops new reports from using it.
      </p>
    </div>
    {#if builds}
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
    {/if}
  </div>

  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

  {#if templates}
    <div class="tabs" role="tablist" aria-label="Templates">
      <button type="button" role="tab" id="tab-in-use" aria-selected={showing === "in-use"} aria-controls="shown-templates"
        onclick={() => (showing = "in-use")}>In use <span class="count">{inUse.length}</span></button>
      <button type="button" role="tab" id="tab-retired" aria-selected={showing === "retired"} aria-controls="shown-templates"
        onclick={() => (showing = "retired")}>Retired <span class="count">{retired.length}</span></button>
    </div>

    <div id="shown-templates" role="tabpanel" aria-labelledby={showing === "retired" ? "tab-retired" : "tab-in-use"}>
      <p class="small muted tab-about">
        {#if showing === "retired"}
          Retired templates make no new reports. Bring one back to use it again{deletes ? "" : "; administrators and managers can delete one for good"}.
          {#if deletes}Deleting one for good takes its versions and pictures with it, once you've typed its name and confirmed it's you.{/if}
        {:else}
          Templates technicians can make reports with once they're published, and drafts on their way there.
          {#if builds}Open one to change its questions, its PDF and its rules.{/if}
        {/if}
      </p>
      {#if shown.length}
        <ul class="cards" aria-label={showing === "retired" ? "Retired templates" : "Templates in use"}>
          {#each shown as t (t.id)}
            {@const href = resolve("/(app)/templates/[id]", { id: String(t.id) })}
            {@const now = status(t)}
            {@const items = menu(t)}
            <li class="card" class:retired={t.retired}>
              <!-- Only for those who open templates: the drawing reads the template. -->
              {#if builds}
                <a class="picture" {href} tabindex="-1" aria-hidden="true"><TemplateCover template={t} {covers} {looks} /></a>
              {/if}
              <div class="title-bar">
                <span class="language" title={t.language === "da" ? "Reports in Danish" : "Reports in English"}>{t.language.toUpperCase()}</span>
                {#if builds}<a class="name" {href} title={t.name}>{t.name}</a>{:else}<span class="name" title={t.name}>{t.name}</span>{/if}
                {#if items.length}<RowMenu label="Actions for {t.name}" {items} />{/if}
              </div>
              <div class="about">
                <p class="small muted when">Created {dateTime(t.created_at)}{t.created_by ? ` · ${t.created_by}` : ""}</p>
                {#if t.description}<p class="small description" title={t.description}>{t.description}</p>{/if}
                {#if t.retired}
                  <p class="small muted when">Retired {dateTime(t.retired_at)}{t.retired_by ? ` · ${t.retired_by}` : ""}</p>
                {:else if t.draft && t.latest_version !== null}
                  <p class="small muted when">Draft changes saved {dateTime(t.draft.saved_at)}{t.draft.saved_by ? ` · ${t.draft.saved_by}` : ""}</p>
                {/if}
              </div>
              <div class="status-bar">
                <span class="small version">
                  {#if t.latest_version !== null}
                    Version {t.latest_version}<span class="muted">{` · ${dateTime(t.published_at)}`}</span>
                  {:else}
                    <span class="muted">Not published yet</span>
                  {/if}
                </span>
                <Pill tone={now.tone} text={now.text} />
              </div>
            </li>
          {/each}
        </ul>
      {:else}
        <section class="empty">
          {#if showing === "retired"}
            <p>No retired templates.</p>
            <p class="small muted">A template retired from its card's menu comes here, out of the way of those in use.</p>
          {:else if templates.length}
            <p>Every template is retired.</p>
            <p class="small muted">Bring one back from the Retired tab{builds ? ", or make a new one" : ""}.</p>
          {:else}
            <p>No templates yet.</p>
            <p class="small muted">{builds ? "Make the first one: its questions, its PDF and its rules, then publish it for technicians." : "Report designers make them."}</p>
          {/if}
        </section>
      {/if}
    </div>
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
  {#if deleting?.latest_version !== null}
    <form id="delete-template" class="stack" onsubmit={(e) => { e.preventDefault(); void remove(); }}>
      <p>
        Delete “{deleting?.name}” for good? Its {deleting?.latest_version === 1 ? "version" : `${deleting?.latest_version} versions`}
        and pictures go with it, and no one can bring it back. The audit log keeps its name and a fingerprint of each version.
      </p>
      <div class="field">
        <label for="delete-name">Type the template's name to confirm</label>
        <input id="delete-name" class="input" autocomplete="off" required bind:value={deleteName} />
      </div>
    </form>
  {:else}
    <p>Delete “{deleting?.name}”? It was never published, so no report uses it. This can't be undone.</p>
  {/if}
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (deleteOpen = false)}>Cancel</button>
    {#if deleting?.latest_version !== null}
      <button class="button button-primary danger-fill" type="submit" form="delete-template"
        disabled={busy || deleteName.trim() !== deleting?.name}>Delete for good</button>
    {:else}
      <button class="button button-primary danger-fill" type="button" disabled={busy} onclick={() => void remove()}>Delete</button>
    {/if}
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
  .tabs {
    display: flex;
    gap: var(--space-1);
    margin-top: calc(-1 * var(--space-3));
    border-bottom: 1px solid var(--border);
  }
  .tabs button {
    padding: var(--space-2) var(--space-3);
    border: 0;
    border-bottom: 2px solid transparent;
    background: none;
    color: var(--text-muted);
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }
  .tabs button:hover {
    color: var(--text);
  }
  .tabs button[aria-selected="true"] {
    border-bottom-color: var(--link);
    color: var(--text);
  }
  .count {
    margin-left: 4px;
    padding: 0 7px;
    border-radius: var(--radius-pill);
    background: var(--surface-subtle);
    color: var(--text-muted);
    font-size: 12px;
  }
  .tab-about {
    margin: var(--space-3) 0;
  }
  /* Cards, as many to a row as fit: the first page, a title bar, what it is, and a
     bar with its version and status. */
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
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
  .title-bar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
    padding: var(--space-2) var(--space-2) var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border);
  }
  .language {
    flex: none;
    padding: 1px 6px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface-subtle);
    color: var(--text-muted);
    font: 600 11px/1.5 var(--font-mono);
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    color: var(--text);
    font-weight: 600;
    text-decoration: none;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  a.name:hover {
    text-decoration: underline;
  }
  .about {
    display: grid;
    flex: 1;
    align-content: start;
    gap: var(--space-1);
    padding: var(--space-3);
  }
  .card .about p {
    margin: 0;
  }
  .description {
    display: -webkit-box;
    overflow: hidden;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .status-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--border);
    background: var(--surface-subtle);
  }
  .version {
    font-weight: 600;
  }
  .version .muted {
    font-weight: 400;
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
