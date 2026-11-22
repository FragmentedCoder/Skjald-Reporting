<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { untrack } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import type { Named } from "#lib/customers.js";
  import { reportsApi, type TemplateChoice } from "#lib/reports/api.js";

  // Starting a report: the template it's written with (its newest published version,
  // which the report stays pinned to), a title, and the site when the project has more
  // than one. Created, the report opens.
  let { open = $bindable(false), projectId, sites }: { open?: boolean; projectId: number; sites: Named[] } = $props();
  const uid = $props.id();

  let templates = $state<TemplateChoice[] | null>(null);
  let templateId = $state("");
  let title = $state("");
  let siteId = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);
  const chosen = $derived(templates?.find((t) => String(t.id) === templateId) ?? null);

  async function load() {
    templates = null;
    templateId = "";
    title = "";
    siteId = "";
    error = null;
    try {
      const found = await reportsApi.templates(projectId);
      templates = found;
      if (found.length === 1) templateId = String(found[0].id);
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The templates couldn't be loaded.";
    }
  }

  // Each time it opens: the templates as they are now, and an empty form.
  $effect(() => {
    if (open) untrack(() => void load());
  });

  async function create(event: SubmitEvent) {
    event.preventDefault();
    if (!chosen) return;
    busy = true;
    error = null;
    try {
      const report = await reportsApi.create(projectId, {
        template_id: chosen.id,
        ...(title.trim() ? { title: title.trim() } : {}),
        site_id: siteId ? Number(siteId) : null,
      });
      open = false;
      await goto(resolve("/(app)/reports/[id]", { id: String(report.id) }));
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The report couldn't be started.";
    } finally {
      busy = false;
    }
  }
</script>

<Dialog bind:open title="New report">
  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
  {#if templates === null}
    {#if !error}<p class="muted">Loading the templates…</p>{/if}
  {:else if !templates.length}
    <p>No template is published yet. A Report Designer publishes templates on the Templates page.</p>
  {:else}
    <form id="{uid}-form" class="stack" onsubmit={create}>
      <div class="field">
        <label for="{uid}-template">Template</label>
        <select id="{uid}-template" class="input" required bind:value={templateId} aria-describedby="{uid}-template-hint">
          <option value="">Choose…</option>
          {#each templates as t (t.id)}<option value={String(t.id)}>{t.name} (version {t.version})</option>{/each}
        </select>
        <span class="hint" id="{uid}-template-hint">
          {#if chosen}{chosen.description ? `${chosen.description} ` : ""}The report gets the next number that starts with {chosen.prefix}, and keeps this version of the template.
          {:else}The report is written with the template's newest version, and keeps it.{/if}
        </span>
      </div>
      <div class="field">
        <label for="{uid}-title">Title <span class="muted">(optional)</span></label>
        <input id="{uid}-title" class="input" maxlength="200" bind:value={title} placeholder={chosen?.name ?? ""} aria-describedby="{uid}-title-hint" />
        <span class="hint" id="{uid}-title-hint">Left empty, the report is titled as its template. It can be changed later.</span>
      </div>
      {#if sites.length > 1}
        <div class="field">
          <label for="{uid}-site">Site</label>
          <select id="{uid}-site" class="input" bind:value={siteId} aria-describedby="{uid}-site-hint">
            <option value="">No site in particular</option>
            {#each sites as site (site.id)}<option value={String(site.id)}>{site.name}</option>{/each}
          </select>
          <span class="hint" id="{uid}-site-hint">The site the report is about. It can be changed later.</span>
        </div>
      {/if}
    </form>
  {/if}
  {#snippet actions()}
    {#if templates?.length}
      <button class="button button-secondary" type="button" onclick={() => (open = false)}>Cancel</button>
      <button class="button button-primary" type="submit" form="{uid}-form" disabled={busy || !chosen}>Start the report</button>
    {:else}
      <button class="button button-secondary" type="button" onclick={() => (open = false)}>Close</button>
    {/if}
  {/snippet}
</Dialog>
