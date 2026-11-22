<script lang="ts">
  import { resolve } from "$app/paths";
  import FileText from "@lucide/svelte/icons/file-text";
  import Plus from "@lucide/svelte/icons/plus";
  import { untrack } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import NewReportDialog from "#lib/components/reports/NewReportDialog.svelte";
  import ReportsTable from "#lib/components/reports/ReportsTable.svelte";
  import { sharedProject } from "#lib/context.js";
  import { CLASSIFICATIONS } from "#lib/customers.js";
  import { dateRange } from "#lib/format.js";
  import { reportsApi, type ReportList } from "#lib/reports/api.js";

  // A project's reports, with what matters about the project beside them. Everyone
  // who may open the project reads them; its technicians start new ones.
  const shared = sharedProject();
  const project = $derived(shared.current);
  const id = $derived(String(project?.id ?? ""));

  let list = $state<ReportList | null>(null);
  let error = $state<string | null>(null);
  let adding = $state(false);

  async function load(projectId: number) {
    try {
      list = await reportsApi.list(projectId);
      error = null;
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The reports couldn't be loaded.";
    }
  }

  // Again whenever the project is: archived or reopened, who may start a report changes.
  $effect(() => {
    const open = project;
    if (open) untrack(() => void load(open.id));
  });
</script>

<svelte:head><title>{pageTitle(project ? `${project.number} ${project.name}` : "Project")}</title></svelte:head>

{#if project}
  <div class="grid">
    <section class="section" aria-labelledby="reports-title">
      <div class="heading-row">
        <h2 class="section-title" id="reports-title">Reports</h2>
        {#if list?.may_create}
          <button class="button button-primary" type="button" onclick={() => (adding = true)}>
            <Plus size={18} aria-hidden="true" />New report
          </button>
        {/if}
      </div>
      {#if error}
        <p class="alert alert-critical" role="alert">{error}</p>
      {:else if list === null}
        <p class="muted">Loading the reports…</p>
      {:else if list.reports.length}
        <ReportsTable reports={list.reports} />
      {:else}
        <div class="empty">
          <FileText size={28} aria-hidden="true" />
          <p>No reports yet.</p>
          <p class="small muted">
            {#if list.may_create}Start one with New report. It's written with a published template, and encrypted with the customer's key.
            {:else if project.archived_at}The project is archived, so no reports are started in it.
            {:else}The project's technicians start its reports.{/if}
          </p>
        </div>
      {/if}
    </section>

    <section class="section" aria-labelledby="glance-title">
      <h2 class="section-title" id="glance-title">At a glance</h2>
      <dl class="facts">
        <dt>Responsible</dt>
        <dd>{project.responsible?.name ?? "Nobody yet"}</dd>
        <dt>Reviewer</dt>
        <dd>{project.reviewer?.name ?? "Nobody yet"}</dd>
        <dt>Dates</dt>
        <dd>{dateRange(project.start_date, project.end_date)}</dd>
        <dt>Shared as</dt>
        <dd>{CLASSIFICATIONS.find((c) => c.value === project.classification)?.hint ?? project.classification}</dd>
        <dt>Team</dt>
        <dd>{project.team.length === 1 ? "1 person" : `${project.team.length} people`}</dd>
      </dl>
      <a class="small" href={resolve("/(app)/projects/[id]/details", { id })}>All details</a>
    </section>
  </div>

  {#if list?.may_create}<NewReportDialog bind:open={adding} projectId={project.id} sites={project.sites} />{/if}
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
  }
  .heading-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-8) var(--space-4);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    color: var(--text-muted);
    text-align: center;
  }
  .empty p:first-of-type {
    color: var(--text);
  }
  @media (max-width: 960px) {
    .grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
