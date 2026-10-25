<script lang="ts">
  import { api, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import ProjectTable from "#lib/components/ProjectTable.svelte";
  import { sharedCustomer } from "#lib/context.js";
  import type { ProjectSummary } from "#lib/customers.js";

  const shared = sharedCustomer();
  const customer = $derived(shared.current);
  const customerId = $derived(customer?.id);
  let archived = $state<ProjectSummary[] | null>(null);

  // Loads for whichever customer is open, and again when it changes.
  $effect(() => {
    const id = customerId;
    if (id === undefined) return;
    api<ProjectSummary[]>("GET", `/customers/${id}/projects?archived=true`)
      .then((found) => (archived = found))
      .catch((e) => {
        if (!sessionGone(e)) archived = [];
      });
  });
</script>

<svelte:head><title>{pageTitle(`Archived · ${customer?.name ?? "Customer"}`)}</title></svelte:head>

<section class="section" aria-labelledby="archived-title">
  <h2 class="section-title" id="archived-title">Archived projects</h2>
  <p class="small muted">
    Finished projects: read-only, with their reports. Retention periods count from the day each
    was archived. A Manager or Administrator can reopen one.
  </p>
  {#if archived}
    <ProjectTable projects={archived} empty="Nothing archived yet." />
  {/if}
</section>
