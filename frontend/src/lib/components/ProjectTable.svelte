<script lang="ts">
  import { resolve } from "$app/paths";
  import { classificationTone, type ProjectSummary } from "#lib/customers.js";
  import { dateRange } from "#lib/format.js";
  import Pill from "./Pill.svelte";

  // Projects in a table, each linking to its own page. With `customer`, a column
  // names whose project it is (for lists across customers). Where the table is
  // narrow, as on a phone, the other columns move under the project's name.
  let {
    projects,
    empty,
    customer = false,
  }: { projects: ProjectSummary[]; empty: string; customer?: boolean } = $props();

  function summary(project: ProjectSummary): string[] {
    return [
      customer ? project.customer.name : null,
      project.responsible?.name ?? "Nobody responsible yet",
      dateRange(project.start_date, project.end_date),
    ].filter((part): part is string => part !== null);
  }
</script>

{#if projects.length}
  <div class="table-wrap projects">
    <table class="table">
      <thead>
        <tr>
          <th>Project</th>
          {#if customer}<th class="roomy">Customer</th>{/if}
          <th class="roomy">Responsible</th>
          <th class="roomy">Dates</th>
          <th class="roomy">Classification</th>
        </tr>
      </thead>
      <tbody>
        {#each projects as project (project.id)}
          <tr>
            <td>
              <a class="row-link" href={resolve("/(app)/projects/[id]", { id: String(project.id) })}>
                {project.name}
              </a>
              <div class="small muted mono">{project.number}</div>
              <div class="small muted compact">
                {#each summary(project) as part, i (i)}{i ? " · " : ""}<span class="nowrap">{part}</span>{/each}
              </div>
              <div class="compact">
                <Pill tone={classificationTone(project.classification)} text={project.classification} />
              </div>
            </td>
            {#if customer}<td class="roomy">{project.customer.name}</td>{/if}
            <td class="roomy">{project.responsible?.name ?? "—"}</td>
            <td class="roomy nowrap">
              {dateRange(project.start_date, project.end_date)}
            </td>
            <td class="roomy"><Pill tone={classificationTone(project.classification)} text={project.classification} /></td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{:else}
  <p class="muted">{empty}</p>
{/if}

<style>
  .projects {
    container-type: inline-size;
  }
  .nowrap {
    white-space: nowrap;
  }
  .compact {
    display: none;
  }
  @container (max-width: 560px) {
    .roomy {
      display: none;
    }
    .compact {
      display: block;
      margin-top: var(--space-1);
    }
  }
</style>
