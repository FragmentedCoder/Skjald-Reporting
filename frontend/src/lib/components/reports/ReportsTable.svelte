<script lang="ts">
  import { resolve } from "$app/paths";
  import Pill from "#lib/components/Pill.svelte";
  import { dateTime } from "#lib/format.js";
  import { statusOf, type Checkout, type ReportSummary } from "#lib/reports/api.js";

  // A project's reports in a table, newest first as the server lists them, each
  // linking to its own page by its number. Where the table is narrow, as on a phone,
  // the other columns move under the number.
  let { reports }: { reports: ReportSummary[] } = $props();

  /** Who has a part of it checked out, each named once. */
  function holders(checkouts: Checkout[]): string {
    return [...new Set(checkouts.map((c) => (c.mine ? "You" : c.holder.name)))].join(", ");
  }

  const template = (report: ReportSummary) => `${report.template.name}, version ${report.template.version}`;
</script>

<div class="table-wrap reports">
  <table class="table">
    <thead>
      <tr>
        <th>Number</th>
        <th class="roomy">Title</th>
        <th class="roomy">Template</th>
        <th class="roomy">State</th>
        <th class="roomy">Started by</th>
        <th class="roomy">Last changed</th>
        <th class="roomy">Checked out by</th>
      </tr>
    </thead>
    <tbody>
      {#each reports as report (report.id)}
        {@const status = statusOf(report.status)}
        {@const held = holders(report.checkouts)}
        <tr>
          <td>
            <a class="row-link mono" href={resolve("/(app)/reports/[id]", { id: String(report.id) })}>{report.number}</a>
            <div class="compact">{report.title}</div>
            <div class="small muted compact">
              {template(report)}{report.author ? ` · started by ${report.author.name}` : ""} · changed {dateTime(report.updated_at)}
            </div>
            {#if held}<div class="small muted compact">Checked out by {held}</div>{/if}
            <div class="compact"><Pill tone={status.tone} text={status.label} /></div>
          </td>
          <td class="roomy title">{report.title}</td>
          <td class="roomy">{template(report)}</td>
          <td class="roomy"><Pill tone={status.tone} text={status.label} /></td>
          <td class="roomy">{report.author?.name ?? "—"}</td>
          <td class="roomy nowrap">{dateTime(report.updated_at)}</td>
          <td class="roomy">{held || "—"}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .reports {
    container-type: inline-size;
  }
  .nowrap {
    white-space: nowrap;
  }
  .title {
    overflow-wrap: anywhere;
  }
  .compact {
    display: none;
  }
  @container (max-width: 720px) {
    .roomy {
      display: none;
    }
    .compact {
      display: block;
      margin-top: var(--space-1);
      overflow-wrap: anywhere;
    }
  }
</style>
