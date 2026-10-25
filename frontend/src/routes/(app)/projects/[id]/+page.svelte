<script lang="ts">
  import { resolve } from "$app/paths";
  import FileText from "@lucide/svelte/icons/file-text";
  import { pageTitle } from "#lib/branding.svelte.js";
  import { sharedProject } from "#lib/context.js";
  import { CLASSIFICATIONS } from "#lib/customers.js";
  import { dateRange } from "#lib/format.js";

  // A project's reports, with what matters about the project beside them.
  const shared = sharedProject();
  const project = $derived(shared.current);
  const id = $derived(String(project?.id ?? ""));
</script>

<svelte:head><title>{pageTitle(project ? `${project.number} ${project.name}` : "Project")}</title></svelte:head>

{#if project}
  <div class="grid">
    <section class="section" aria-labelledby="reports-title">
      <h2 class="section-title" id="reports-title">Reports</h2>
      <div class="empty">
        <FileText size={28} aria-hidden="true" />
        <p>No reports yet.</p>
        <p class="small muted">
          Reports arrive with the template builder. They'll be written, reviewed and signed here,
          encrypted with the customer's key.
        </p>
      </div>
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
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
    gap: var(--space-4);
    align-items: start;
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
