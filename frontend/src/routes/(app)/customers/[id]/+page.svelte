<script lang="ts">
  import { resolve } from "$app/paths";
  import Plus from "@lucide/svelte/icons/plus";
  import { pageTitle } from "#lib/branding.svelte.js";
  import ProjectTable from "#lib/components/ProjectTable.svelte";
  import { sharedCustomer } from "#lib/context.js";
  import { dateTime } from "#lib/format.js";
  import { roleName } from "#lib/roles.js";
  import { workspace } from "#lib/workspace.svelte.js";

  // A customer at a glance: its work under way, who to talk to, who works on it.
  const shared = sharedCustomer();
  const customer = $derived(shared.current);
  const id = $derived(String(customer?.id ?? ""));
  const recent = $derived((workspace.projects ?? []).slice(0, 5));
</script>

<svelte:head><title>{pageTitle(customer?.name ?? "Customer")}</title></svelte:head>

{#if customer}
  <div class="grid">
    <section class="section wide" aria-labelledby="work-title">
      <div class="heading-row">
        <h2 class="section-title" id="work-title">Projects under way</h2>
        {#if customer.may_create_projects}
          <a class="button button-primary" href={resolve("/(app)/customers/[id]/projects/new", { id })}>
            <Plus size={18} aria-hidden="true" />New project
          </a>
        {/if}
      </div>
      <ProjectTable projects={recent} empty={customer.may_create_projects
        ? "No active projects. Start one with New project."
        : "No active projects you can open."} />
      {#if (customer.active_projects ?? 0) > recent.length}
        <a class="small" href={resolve("/(app)/customers/[id]/projects", { id })}>
          All {customer.active_projects} projects
        </a>
      {/if}
    </section>

    <section class="section" aria-labelledby="contacts-title">
      <h2 class="section-title" id="contacts-title">Contacts</h2>
      {#if customer.contacts?.length}
        <ul class="plain">
          {#each customer.contacts.slice(0, 4) as contact (contact.id)}
            <li>
              <span class="check-title">{contact.name}</span>
              <span class="small muted">{[contact.role, contact.email, contact.phone].filter(Boolean).join(" · ")}</span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="muted">No contacts yet.</p>
      {/if}
      <a class="small" href={resolve("/(app)/customers/[id]/contacts", { id })}>Contacts & sites</a>
    </section>

    <section class="section" aria-labelledby="people-title">
      <h2 class="section-title" id="people-title">People on this customer</h2>
      {#if customer.assigned?.length}
        <ul class="plain">
          {#each customer.assigned as person (person.id)}
            <li>
              <span class="check-title">{person.display_name}</span>
              <span class="small muted">{person.roles.map(roleName).join(", ")}</span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="muted">Nobody is assigned yet.</p>
      {/if}
      <a class="small" href={resolve("/(app)/customers/[id]/people", { id })}>People</a>
    </section>

    <section class="section wide" aria-labelledby="facts-title">
      <h2 class="section-title" id="facts-title">Details</h2>
      <dl class="facts">
        <dt>Address</dt>
        <dd class="address">{customer.address || "—"}</dd>
        <dt>Sites</dt>
        <dd>{customer.sites?.map((s) => s.name).join(", ") || "—"}</dd>
        <dt>Raw data kept</dt>
        <dd>{customer.retention_months} months after a project is archived</dd>
        <dt>Projects</dt>
        <dd>{customer.active_projects} active, {customer.archived_projects} archived</dd>
        <dt>Added</dt>
        <dd>{dateTime(customer.created_at)}</dd>
      </dl>
      <p class="small muted">
        Everything here is encrypted with this customer's own key.
      </p>
    </section>
  </div>
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }
  .wide {
    grid-column: 1 / -1;
  }
  .heading-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }
  .plain {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .plain li {
    display: flex;
    flex-direction: column;
  }
  .address {
    white-space: pre-line;
  }
  @media (max-width: 760px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
