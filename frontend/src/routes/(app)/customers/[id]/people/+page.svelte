<script lang="ts">
  import BadgeCheck from "@lucide/svelte/icons/badge-check";
  import PenLine from "@lucide/svelte/icons/pen-line";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import RoleGroups, { ROLE_GROUPS } from "#lib/components/RoleGroups.svelte";
  import { sharedCustomer } from "#lib/context.js";
  import { reviewers, technicians, type CustomerDetail } from "#lib/customers.js";
  import { toast } from "#lib/toast.svelte.js";

  // Who works with the customer, and as what: technicians do the work, reviewers
  // check it. Someone with both roles can be either here, or both. Managers and
  // Administrators choose; everyone sees who.
  const shared = sharedCustomer();
  const customer = $derived(shared.current);
  // Start from who's assigned now; the checkboxes change them until they're saved.
  let asTechnician = $derived(technicians(customer?.assigned ?? null).map((p) => p.id));
  let asReviewer = $derived(reviewers(customer?.assigned ?? null).map((p) => p.id));
  let busy = $state(false);

  const sections = $derived([
    { role: "technician" as const, icon: PenLine,
      people: (customer?.assignable ?? []).filter((p) => p.roles.includes("technician")) },
    { role: "reviewer" as const, icon: BadgeCheck,
      people: (customer?.assignable ?? []).filter((p) => p.roles.includes("reviewer")) },
  ]);

  async function save(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    try {
      shared.use(await api<CustomerDetail>("PUT", `/customers/${customer?.id}/assignments`,
        { technicians: asTechnician, reviewers: asReviewer }));
      toast("Who works with this customer is saved.", "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "Something went wrong.", "critical");
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{pageTitle(`People · ${customer?.name ?? "Customer"}`)}</title></svelte:head>

{#if customer}
  <section class="section" aria-labelledby="people-title">
    <h2 class="section-title" id="people-title">Who works with this customer</h2>
    <p class="small muted">
      Technicians and reviewers see only the customers they're assigned to. Someone with both roles
      can be a technician for one customer and its reviewer for another, or both. A TLP:RED project
      is only for its own team, chosen on the project.
    </p>
    {#if customer.may_manage}
      <form class="stack" onsubmit={save}>
        {#if customer.assignable?.length}
          <div class="roles">
            {#each sections as section (section.role)}
              {@const about = ROLE_GROUPS[section.role]}
              <fieldset class="checks role {section.role}">
                <legend class="role-title">
                  <section.icon size={16} aria-hidden="true" />{about.title}
                </legend>
                <p class="small muted">{about.about}</p>
                {#each section.people as person (person.id)}
                  <label class="check">
                    {#if section.role === "technician"}
                      <input type="checkbox" value={person.id} bind:group={asTechnician} />
                    {:else}
                      <input type="checkbox" value={person.id} bind:group={asReviewer} />
                    {/if}
                    <span>
                      <span class="check-title">{person.display_name}</span>
                      <span class="small muted">
                        {person.roles.includes("technician") && person.roles.includes("reviewer")
                          ? "Technician and reviewer · " : ""}<span class="mono">{person.username}</span>
                      </span>
                    </span>
                  </label>
                {:else}
                  <p class="small muted">Nobody has this role yet. Give someone it in Admin → Users.</p>
                {/each}
              </fieldset>
            {/each}
          </div>
          <div><button class="button button-primary" type="submit" disabled={busy}>Save</button></div>
        {:else}
          <p class="muted">
            Nobody has the Technician or Reviewer role yet. Give someone a role in Admin → Users,
            then assign them here.
          </p>
        {/if}
      </form>
    {:else}
      <RoleGroups groups={[
        { role: "technician", empty: "No technicians yet.",
          people: technicians(customer.assigned).map((p) => ({ id: p.id, name: p.display_name })) },
        { role: "reviewer", empty: "No reviewers yet.",
          people: reviewers(customer.assigned).map((p) => ({ id: p.id, name: p.display_name })) },
      ]} />
    {/if}
  </section>
{/if}

<style>
  .roles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: var(--space-4);
  }
  .role {
    margin: 0;
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-left: 3px solid var(--link);
    border-radius: var(--radius-md);
  }
  .role.reviewer {
    border-left-color: var(--accent);
  }
  .role-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-1);
    font: var(--type-label);
  }
</style>
