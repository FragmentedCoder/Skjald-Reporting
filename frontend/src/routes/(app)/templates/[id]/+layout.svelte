<script lang="ts">
  import { beforeNavigate } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import Pencil from "@lucide/svelte/icons/pencil";
  import { untrack, type Snippet } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import { dateTime, time } from "#lib/format.js";
  import { templatesApi, type Changes } from "#lib/templates/api.js";
  import { Draft, shareDraft } from "#lib/templates/draft.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  // A template's builder: its header (name, whether the draft is saved, its
  // problems, Publish) and tabs. The draft is saved a moment after each change.
  let { children }: { children: Snippet } = $props();

  const draft = new Draft();
  shareDraft(draft);

  const id = $derived(Number(page.params.id));
  const base = $derived(resolve("/(app)/templates/[id]", { id: String(id) }));
  const tabs = $derived([
    { href: base, label: "Questions" },
    { href: resolve("/(app)/templates/[id]/layout", { id: String(id) }), label: "Layout" },
    { href: resolve("/(app)/templates/[id]/settings", { id: String(id) }), label: "Settings" },
    { href: resolve("/(app)/templates/[id]/versions", { id: String(id) }), label: "Versions" },
  ]);

  $effect(() => {
    const wanted = id;
    untrack(() => void draft.load(wanted).catch((e) => {
      if (sessionGone(e)) return;
    }));
  });

  // Every change to the content, however deep, reaches the draft.
  $effect(() => {
    const text = JSON.stringify(draft.content);
    untrack(() => draft.noticed(text));
  });

  beforeNavigate(({ to, cancel, willUnload }) => {
    if (!draft.unsaved) return;
    if (willUnload) {
      cancel();
      return;
    }
    if (!to?.url.pathname.startsWith(base)) void draft.save();
  });

  let renaming = $state(false);
  let newName = $state("");
  let newDescription = $state("");

  async function rename(event: SubmitEvent) {
    event.preventDefault();
    try {
      draft.template = await templatesApi.update(id, { name: newName.trim(), description: newDescription.trim() });
      renaming = false;
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The name could not be changed.", "critical");
    }
  }

  let publishing = $state(false);
  let note = $state("");
  let changes = $state<Changes | null>(null);
  let busy = $state(false);

  async function openPublish() {
    note = "";
    changes = null;
    publishing = true;
    await draft.save();
    try {
      changes = await templatesApi.changes(id);
    } catch {
      changes = null;
    }
  }

  async function publish() {
    busy = true;
    try {
      const number = await draft.publish(note.trim());
      publishing = false;
      toast(`Version ${number} is published. New reports use it.`, "ok");
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The template could not be published.", "critical");
    } finally {
      busy = false;
    }
  }

  async function edit() {
    try {
      await draft.edit();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "A draft could not be started.", "critical");
    }
  }

  const count = $derived(draft.problems.length);
  const totalChanges = $derived(
    changes
      ? changes.questions_added.length + changes.questions_removed.length + changes.questions_changed.length
        + changes.blocks_added.length + changes.blocks_removed.length + changes.blocks_changed.length
        + changes.settings_changed.length
      : 0,
  );
</script>

<svelte:head><title>{pageTitle(draft.template?.name ?? "Template")}</title></svelte:head>

<svelte:window onbeforeunload={(event) => { if (draft.unsaved) event.preventDefault(); }} />

<main class="page-content builder">
  <a class="back small" href={resolve("/(app)/templates")}><ChevronLeft size={16} aria-hidden="true" /> Templates</a>

  {#if draft.loadError}
    <p class="alert alert-critical" role="alert">{draft.loadError}</p>
  {:else if draft.template && draft.content}
    <header class="head">
      <div class="identity">
        <p class="overline">Template · {draft.content.settings.prefix}</p>
        <h1 class="title">
          {draft.template.name}
          <button class="icon-button" type="button" aria-label="Rename the template" title="Rename"
            onclick={() => { newName = draft.template?.name ?? ""; newDescription = draft.template?.description ?? ""; renaming = true; }}>
            <Pencil size={16} aria-hidden="true" />
          </button>
        </h1>
        <p class="status small" aria-live="polite">
          {#if draft.readonly}
            <Pill tone="ok" text="Version {draft.shownVersion}" />
            <span class="muted">Published {dateTime(draft.template.published_at)}. Editing starts a new draft.</span>
          {:else}
            <Pill tone="info" text="Draft" />
            <span class="muted">
              {#if draft.saveState === "saving"}Saving…
              {:else if draft.saveState === "unsaved"}Unsaved changes
              {:else if draft.saveState === "saved"}Saved{draft.savedAt ? ` at ${time(draft.savedAt)}` : ""}
              {/if}
            </span>
            {#if draft.template.latest_version !== null}
              <span class="muted">· Version {draft.template.latest_version} is the one in use.</span>
            {/if}
          {/if}
        </p>
      </div>
      <div class="actions">
        {#if !draft.readonly}
          <a class="problems" href="#problems" class:none={count === 0}>
            <Pill tone={count ? "warning" : "ok"} text={count ? `${count} problem${count === 1 ? "" : "s"}` : "No problems"} />
          </a>
        {/if}
        {#if draft.readonly}
          <button class="button button-primary" type="button" onclick={edit}>Edit</button>
        {:else}
          <button class="button button-primary" type="button" onclick={openPublish} disabled={count > 0}
            title={count ? "Fix the problems first" : undefined}>Publish</button>
        {/if}
      </div>
    </header>

    {#if draft.saveState === "conflict"}
      <div class="alert alert-warning conflict" role="alert">
        <p>{draft.saveMessage}</p>
        <div class="button-row">
          <button class="button button-secondary" type="button" onclick={() => void draft.reload()}>Reload theirs</button>
          <button class="button button-secondary" type="button" onclick={() => void draft.keepMine()}>Keep mine</button>
        </div>
      </div>
    {:else if draft.saveState === "failed"}
      <div class="alert alert-critical" role="alert">
        <p>{draft.saveMessage}</p>
        <button class="button button-secondary" type="button" onclick={() => void draft.save()}>Try again</button>
      </div>
    {/if}

    <nav class="tabs" aria-label="Template">
      {#each tabs as tab (tab.href)}
        <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- every tab's href comes from resolve() -->
        <a href={tab.href} aria-current={page.url.pathname === tab.href ? "page" : undefined}>{tab.label}</a>
      {/each}
    </nav>

    {@render children()}
  {:else}
    <p class="muted">Loading…</p>
  {/if}
</main>

<Dialog bind:open={renaming} title="Rename template">
  <form id="rename-template" class="stack" onsubmit={rename}>
    <div class="field">
      <label for="rename-name">Name</label>
      <input id="rename-name" class="input" bind:value={newName} required maxlength="200" />
    </div>
    <div class="field">
      <label for="rename-description">Description <span class="muted">(optional)</span></label>
      <textarea id="rename-description" class="input" rows="2" bind:value={newDescription} maxlength="1000"></textarea>
    </div>
  </form>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (renaming = false)}>Cancel</button>
    <button class="button button-primary" type="submit" form="rename-template" disabled={!newName.trim()}>Save</button>
  {/snippet}
</Dialog>

<Dialog bind:open={publishing} title="Publish version {(draft.template?.latest_version ?? 0) + 1}">
  <div class="stack">
    <p class="small">New reports use the published version, and it never changes. Reports already made keep the version they started with.</p>
    {#if changes && draft.template?.latest_version !== null}
      {#if totalChanges}
        <div class="changes small">
          <p class="overline">Changes since version {draft.template?.latest_version}</p>
          <ul>
            {#each changes.questions_added as q (q.id)}<li>Question added: {q.label}</li>{/each}
            {#each changes.questions_removed as q (q.id)}<li>Question removed: {q.label}</li>{/each}
            {#each changes.questions_changed as q (q.id)}<li>Question changed: {q.label}</li>{/each}
            {#each changes.blocks_added as b (b.id)}<li>Block added: {b.label}</li>{/each}
            {#each changes.blocks_removed as b (b.id)}<li>Block removed: {b.label}</li>{/each}
            {#each changes.blocks_changed as b (b.id)}<li>Block changed: {b.label}</li>{/each}
            {#if changes.settings_changed.length}<li>Settings changed: {changes.settings_changed.join(", ")}</li>{/if}
          </ul>
        </div>
      {:else}
        <p class="small muted">Nothing changed since version {draft.template?.latest_version}.</p>
      {/if}
    {/if}
    <div class="field">
      <label for="publish-note">What changed <span class="muted">(optional)</span></label>
      <textarea id="publish-note" class="input" rows="2" bind:value={note} maxlength="500"></textarea>
      <span class="hint">Kept with the version, for other designers.</span>
    </div>
  </div>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (publishing = false)}>Cancel</button>
    <button class="button button-primary" type="button" onclick={publish} disabled={busy}>Publish</button>
  {/snippet}
</Dialog>

<style>
  .builder {
    max-width: none;
  }
  .back {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    color: var(--text-muted);
    text-decoration: none;
  }
  .back:hover {
    color: var(--link);
  }
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-4);
  }
  .overline {
    margin: 0;
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .status {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .problems {
    text-decoration: none;
  }
  .problems.none {
    pointer-events: none;
  }
  .icon-button {
    display: inline-grid;
    place-items: center;
    width: 32px;
    height: 32px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .icon-button:hover {
    border-color: var(--border);
    color: var(--text);
  }
  .conflict p {
    margin: 0 0 var(--space-2);
  }
  .tabs {
    display: flex;
    gap: var(--space-1);
    overflow-x: auto;
    border-bottom: 1px solid var(--border);
  }
  .tabs a {
    padding: var(--space-2) var(--space-3);
    border-bottom: 2px solid transparent;
    color: var(--text-muted);
    font-weight: 600;
    font-size: 14px;
    text-decoration: none;
    white-space: nowrap;
  }
  .tabs a:hover {
    color: var(--text);
  }
  .tabs a[aria-current="page"] {
    border-bottom-color: var(--link);
    color: var(--text);
  }
  .changes ul {
    margin: var(--space-1) 0 0;
    padding-left: var(--space-4);
  }
</style>
