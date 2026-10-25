<script lang="ts">
  import { resolve } from "$app/paths";
  import Plus from "@lucide/svelte/icons/plus";
  import { pageTitle } from "#lib/branding.svelte.js";
  import ProjectTable from "#lib/components/ProjectTable.svelte";
  import { sharedCustomer } from "#lib/context.js";
  import { workspace } from "#lib/workspace.svelte.js";

  const shared = sharedCustomer();
  const customer = $derived(shared.current);
</script>

<svelte:head><title>{pageTitle(`Projects · ${customer?.name ?? "Customer"}`)}</title></svelte:head>

{#if customer}
  <section class="section" aria-labelledby="projects-title">
    <div class="heading-row">
      <h2 class="section-title" id="projects-title">Projects</h2>
      {#if customer.may_manage_projects}
        <a class="button button-primary"
          href={resolve("/(app)/customers/[id]/projects/new", { id: String(customer.id) })}>
          <Plus size={18} aria-hidden="true" />New project
        </a>
      {/if}
    </div>
    <p class="small muted">
      The work under way for this customer. Managers and Administrators start, change and archive
      projects; archiving makes a project and its reports read-only, and retention counts from
      then. TLP:RED projects are listed only for Managers, Administrators and their team.
    </p>
    <ProjectTable projects={workspace.projects ?? []}
      empty={customer.may_manage_projects
        ? "No active projects. Start one with New project."
        : "No active projects you can open."} />
  </section>
{/if}

<style>
  .heading-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }
</style>
