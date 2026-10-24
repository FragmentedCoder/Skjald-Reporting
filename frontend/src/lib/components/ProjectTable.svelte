<script lang="ts">
  import { resolve } from "$app/paths";
  import { classificationTone, type ProjectSummary } from "#lib/customers.js";
  import { date } from "#lib/format.js";
  import Pill from "./Pill.svelte";

  // Projects in a table, each linking to its own page. With `customer`, a column
  // names whose project it is (for lists across customers).
  let {
    projects,
    empty,
    customer = false,
  }: { projects: ProjectSummary[]; empty: string; customer?: boolean } = $props();
</script>

{#if projects.length}
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Project</th>
          {#if customer}<th>Customer</th>{/if}
          <th>Responsible</th>
          <th>Dates</th>
          <th>Classification</th>
        </tr>
      </thead>
      <tbody>
        {#each projects as project (project.id)}
          <tr>
            <td>
              <a class="row-link" href={resolve("/projects/[id]", { id: String(project.id) })}>
                {project.name}
              </a>
              <div class="small muted mono">{project.number}</div>
            </td>
            {#if customer}<td>{project.customer.name}</td>{/if}
            <td>{project.responsible?.name ?? "—"}</td>
            <td class="nowrap">
              {project.start_date || project.end_date
                ? `${date(project.start_date)} – ${date(project.end_date)}`
                : "—"}
            </td>
            <td><Pill tone={classificationTone(project.classification)} text={project.classification} /></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{:else}
  <p class="muted">{empty}</p>
{/if}

<style>
  .nowrap {
    white-space: nowrap;
  }
</style>
