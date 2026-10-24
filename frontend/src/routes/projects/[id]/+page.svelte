<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import Archive from "@lucide/svelte/icons/archive";
  import ArchiveRestore from "@lucide/svelte/icons/archive-restore";
  import { onMount } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import AppShell from "#lib/components/AppShell.svelte";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import ProjectFields, { projectBody, type ProjectForm } from "#lib/components/ProjectFields.svelte";
  import { classificationTone, type CustomerDetail, type ProjectDetail } from "#lib/customers.js";
  import { date, dateTime } from "#lib/format.js";
  import { settle, type SessionInfo } from "#lib/session.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  let info = $state<SessionInfo | null>(null);
  let project = $state<ProjectDetail | null>(null);
  let customer = $state<CustomerDetail | null>(null);
  let form = $state<ProjectForm | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);
  let archiveOpen = $state(false);

  const id = $derived(page.params.id ?? "");

  function use(found: ProjectDetail) {
    project = found;
    form = {
      name: found.name,
      start_date: found.start_date ?? "",
      end_date: found.end_date ?? "",
      responsible_id: found.responsible ? String(found.responsible.id) : "",
      contact_id: found.contact ? String(found.contact.id) : "",
      site_ids: found.sites.map((s) => s.id),
      classification: found.classification,
    };
  }

  onMount(async () => {
    info = await settle("app");
    if (!info) return;
    try {
      use(await api<ProjectDetail>("GET", `/projects/${id}`));
      if (project?.may_edit) customer = await api<CustomerDetail>("GET", `/customers/${project.customer.id}`);
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Not found.";
    }
  });

  async function run(action: () => Promise<ProjectDetail>, done: string) {
    busy = true;
    error = null;
    try {
      use(await action());
      toast(done, "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
    } finally {
      busy = false;
    }
  }

  function save(event: SubmitEvent) {
    event.preventDefault();
    if (form) run(() => api("PATCH", `/projects/${id}`, projectBody(form!)), "Project saved.");
  }

  function archive() {
    archiveOpen = false;
    run(() => api("POST", `/projects/${id}/archive`), "Archived: the project is read-only now.");
  }
</script>

<svelte:head><title>{pageTitle(project ? `${project.number} ${project.name}` : "Project")}</title></svelte:head>

{#if info}
  <AppShell {info}>
    <main class="page-content">
      <div class="page-header">
        <div>
          {#if project}
            <a class="small" href={resolve("/customers/[id]", { id: String(project.customer.id) })}>
              {project.customer.name}
            </a>
          {/if}
          <h1 class="title">{project?.name ?? "Project"}</h1>
          {#if project}
            <div class="tags">
              <span class="small muted mono">{project.number}</span>
              <Pill tone={classificationTone(project.classification)} text={project.classification} />
              {#if project.archived_at}<Pill tone="neutral" text="Archived" />{/if}
            </div>
          {/if}
        </div>
        {#if project?.may_edit}
          <button class="button button-secondary" type="button" disabled={busy}
            onclick={() => (archiveOpen = true)}>
            <Archive size={16} aria-hidden="true" />Archive project
          </button>
        {:else if project?.may_reopen}
          <button class="button button-secondary" type="button" disabled={busy}
            onclick={() => run(() => api("POST", `/projects/${id}/reopen`), "Reopened: the project can be changed again.")}>
            <ArchiveRestore size={16} aria-hidden="true" />Reopen project
          </button>
        {/if}
      </div>

      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

      {#if project}
        {#if project.archived_at}
          <p class="alert alert-info">
            Archived {dateTime(project.archived_at)}. The project and its reports are read-only, and
            retention periods count from this date.
          </p>
        {/if}

        <section class="section" aria-labelledby="reports-title">
          <h2 class="section-title" id="reports-title">Reports</h2>
          <p class="muted">Reports arrive with the template builder; they'll be listed here.</p>
        </section>

        {#if project.may_edit && form && customer}
          <form class="section stack form-wide" onsubmit={save} aria-labelledby="edit-title">
            <h2 class="section-title" id="edit-title">Project</h2>
            <p class="small muted">Reports fill these in. Changes are logged.</p>
            <ProjectFields bind:values={form} {customer} />
            <div><button class="button button-primary" type="submit" disabled={busy}>Save project</button></div>
          </form>
        {:else}
          <section class="section" aria-labelledby="facts-title">
            <h2 class="section-title" id="facts-title">Project</h2>
            <dl class="facts">
              <dt>Responsible</dt>
              <dd>{project.responsible?.name ?? "Nobody yet"}</dd>
              <dt>Dates</dt>
              <dd>{project.start_date || project.end_date ? `${date(project.start_date)} – ${date(project.end_date)}` : "—"}</dd>
              <dt>Customer contact</dt>
              <dd>{project.contact?.name ?? "None"}</dd>
              <dt>Sites</dt>
              <dd>{project.sites.map((s) => s.name).join(", ") || "—"}</dd>
              <dt>Created</dt>
              <dd>{dateTime(project.created_at)}</dd>
            </dl>
          </section>
        {/if}
      {/if}
    </main>
  </AppShell>

  <Dialog bind:open={archiveOpen} title="Archive {project?.number ?? 'project'}">
    <p>
      The project and its reports become read-only, and it moves to the customer's Archived tab.
      Retention periods count from today. An administrator can reopen it.
    </p>
    {#snippet actions()}
      <button class="button button-secondary" type="button" onclick={() => (archiveOpen = false)}>Cancel</button>
      <button class="button button-primary" type="button" onclick={archive}>Archive project</button>
    {/snippet}
  </Dialog>
{/if}

<style>
  .tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-1);
  }
  .form-wide {
    max-width: 680px;
  }
</style>
