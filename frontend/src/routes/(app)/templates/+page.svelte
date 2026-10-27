<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import Archive from "@lucide/svelte/icons/archive";
  import ArchiveRestore from "@lucide/svelte/icons/archive-restore";
  import Copy from "@lucide/svelte/icons/copy";
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import { onMount } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import RowMenu, { type MenuItem } from "#lib/components/RowMenu.svelte";
  import { dateTime } from "#lib/format.js";
  import { templatesApi, type TemplateSummary } from "#lib/templates/api.js";
  import { toast } from "#lib/toast.svelte.js";

  // Every template, for those who build them: what's published, what's in a draft.
  let templates = $state<TemplateSummary[] | null>(null);
  let error = $state<string | null>(null);

  let adding = $state(false);
  let name = $state("");
  let description = $state("");
  let busy = $state(false);

  let copying = $state<TemplateSummary | null>(null);
  let copyOpen = $state(false);
  let copyName = $state("");
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
      const created = await templatesApi.copy(copying.id, copyName.trim());
      copyOpen = false;
      toast(`“${created.name}” is a new template, as a draft.`, "ok");
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The template could not be copied.", "critical");
    } finally {
      busy = false;
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
      { label: "Copy", icon: Copy, run: () => { copying = t; copyName = `${t.name} (copy)`; copyOpen = true; } },
    ];
    if (t.retired) items.push({ label: "Bring back", icon: ArchiveRestore, run: () => act(() => templatesApi.restore(t.id), `“${t.name}” can be used again.`) });
    else if (t.latest_version !== null) items.push({ label: "Retire", icon: Archive, run: () => act(() => templatesApi.retire(t.id), `“${t.name}” is retired: no new reports use it.`) });
    if (t.latest_version === null) items.push({ label: "Delete", icon: X, danger: true, run: () => { deleting = t; deleteOpen = true; } });
    return items;
  }

  onMount(load);
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
    <button class="button button-primary" type="button" onclick={() => { adding = true; name = ""; description = ""; }}>
      <Plus size={18} aria-hidden="true" />
      New template
    </button>
  </div>

  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

  {#if templates}
    {#if templates.length}
      <div class="section table-wrap">
        <table class="table">
          <thead>
            <tr><th>Name</th><th>Published</th><th class="roomy">Draft</th><th><span class="visually-hidden">Actions</span></th></tr>
          </thead>
          <tbody>
            {#each templates as t (t.id)}
              <tr class:retired={t.retired}>
                <td>
                  <a class="row-link" href={resolve("/(app)/templates/[id]", { id: String(t.id) })}>{t.name}</a>
                  {#if t.retired}<Pill tone="neutral" text="Retired" />{/if}
                  {#if t.description}<span class="small muted description">{t.description}</span>{/if}
                </td>
                <td>
                  {#if t.latest_version !== null}
                    Version {t.latest_version}
                    <span class="small muted">{dateTime(t.published_at ?? "")}</span>
                  {:else}
                    <span class="muted">Not yet</span>
                  {/if}
                </td>
                <td class="roomy">
                  {#if t.draft}
                    <Pill tone="info" text="Draft" />
                    <span class="small muted">{t.draft.saved_by ?? "Someone"}, {dateTime(t.draft.saved_at)}</span>
                  {:else}
                    <span class="muted">None</span>
                  {/if}
                </td>
                <td class="actions"><RowMenu label="Actions for {t.name}" items={menu(t)} /></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
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

<Dialog bind:open={copyOpen} title="Copy template">
  <form id="copy-template" class="stack" onsubmit={copy}>
    <p class="small muted">The copy starts as a draft of its own, from {copying?.draft ? "the draft" : "the newest version"}, images included. Copy a template to translate it.</p>
    <div class="field">
      <label for="copy-name">Name of the copy</label>
      <input id="copy-name" class="input" bind:value={copyName} required maxlength="200" />
    </div>
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
  .description {
    display: block;
  }
  .danger-fill {
    background: var(--critical-text);
    color: var(--surface);
  }
  .retired .row-link {
    color: var(--text-muted);
  }
  .actions {
    width: 1%;
    text-align: right;
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
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-8);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    text-align: center;
  }
</style>
