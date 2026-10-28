<script lang="ts">
  import { ApiError, sessionGone } from "#lib/api.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import { dateTime } from "#lib/format.js";
  import { templatesApi } from "#lib/templates/api.js";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  // Every published version, newest first, with who published it and why. Versions
  // never change; a new draft can start from any of them.
  const draft = useDraft();
  const template = $derived(draft.template);

  let discarding = $state(false);

  // The browser saves the .skjald file the server sends as an attachment.
  function download(number?: number) {
    if (template) window.location.assign(templatesApi.exportUrl(template.id, number));
  }

  async function startFrom(number: number) {
    try {
      await templatesApi.startDraft(draft.id, number);
      await draft.load(draft.id);
      toast(`A new draft starts from version ${number}.`, "ok");
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "A draft could not be started.", "critical");
    }
  }

  async function discard() {
    discarding = false;
    try {
      await draft.discard();
      toast("The draft is discarded.", "ok");
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The draft could not be discarded.", "critical");
    }
  }
</script>

{#if template}
  <section class="section versions">
    <h2 class="section-title">Versions</h2>
    {#if template.draft && template.latest_version !== null}
      <div class="draft-line">
        <p class="small">There's a draft, saved by {template.draft.saved_by ?? "someone"} {dateTime(template.draft.saved_at)}.</p>
        <button class="button button-secondary" type="button" onclick={() => (discarding = true)}>Discard the draft</button>
      </div>
    {/if}
    {#if template.versions.length}
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Version</th><th>Published</th><th>What changed</th><th><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>
            {#each template.versions as version, i (version.number)}
              <tr>
                <td>Version {version.number} {#if i === 0}<Pill tone="ok" text="In use" />{/if}</td>
                <td>{dateTime(version.published_at)}<span class="small muted"> by {version.published_by ?? "someone"}</span></td>
                <td>{version.note || "—"}<span class="small muted mono hash" title="SHA-256 of the version">{version.content_sha256.slice(0, 12)}</span></td>
                <td class="actions">
                  <button class="button button-secondary" type="button" onclick={() => download(version.number)}>Export</button>
                  {#if !template.draft}
                    <button class="button button-secondary" type="button" onclick={() => startFrom(version.number)}>Start a draft from it</button>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="small muted">A published version never changes, and reports keep the version they were made with.</p>
    {:else}
      <p class="small muted">Nothing is published yet. Publish the draft when it has no problems.</p>
      <p><button class="button button-secondary" type="button" onclick={() => download()}>Export the draft</button></p>
    {/if}
    <p class="small muted">An export is a .skjald file for another Skjald install (Templates → Import), with the shared library entries the template reads and the company's default style. Its strings.json holds every piece of text, for translating outside Skjald.</p>
  </section>
{/if}

<Dialog bind:open={discarding} title="Discard the draft?">
  <p>Every change since version {template?.latest_version} is lost. Reports keep using version {template?.latest_version}.</p>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (discarding = false)}>Keep it</button>
    <button class="button button-primary" type="button" onclick={discard}>Discard</button>
  {/snippet}
</Dialog>

<style>
  .versions {
    margin-top: var(--space-4);
  }
  .draft-line {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    margin-bottom: var(--space-3);
  }
  .draft-line p {
    margin: 0;
  }
  .hash {
    display: block;
  }
  .actions {
    text-align: right;
  }
</style>
