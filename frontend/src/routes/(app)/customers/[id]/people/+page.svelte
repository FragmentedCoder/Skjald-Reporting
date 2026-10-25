<script lang="ts">
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import { sharedCustomer } from "#lib/context.js";
  import type { CustomerDetail } from "#lib/customers.js";
  import { roleName } from "#lib/roles.js";
  import { toast } from "#lib/toast.svelte.js";

  // Who works with the customer. Administrators choose; everyone sees who.
  const shared = sharedCustomer();
  const customer = $derived(shared.current);
  // Starts from who's assigned now; the checkboxes change it until it's saved.
  let people = $derived((customer?.assigned ?? []).map((p) => p.id));
  let busy = $state(false);

  async function save(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    try {
      shared.use(await api<CustomerDetail>("PUT", `/customers/${customer?.id}/assignments`,
        { user_ids: people }));
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
      Technicians and reviewers see only the customers they're assigned to. Technicians create
      projects and reports for them; reviewers review and countersign. A TLP:RED project is
      only for its own team, chosen on the project.
    </p>
    {#if customer.may_manage}
      <form class="stack" onsubmit={save}>
        {#if customer.assignable?.length}
          <fieldset class="checks people">
            <legend class="visually-hidden">Assigned people</legend>
            {#each customer.assignable as person (person.id)}
              <label class="check">
                <input type="checkbox" value={person.id} bind:group={people} />
                <span>
                  <span class="check-title">{person.display_name}</span>
                  <span class="small muted">
                    {person.roles.filter((r) => r === "technician" || r === "reviewer").map(roleName).join(", ")}
                    · <span class="mono">{person.username}</span>
                  </span>
                </span>
              </label>
            {/each}
          </fieldset>
          <div><button class="button button-primary" type="submit" disabled={busy}>Save</button></div>
        {:else}
          <p class="muted">
            Nobody has the Technician or Reviewer role yet. Give someone a role in Admin → Users,
            then assign them here.
          </p>
        {/if}
      </form>
    {:else if customer.assigned?.length}
      <ul class="plain">
        {#each customer.assigned as person (person.id)}
          <li>{person.display_name} <span class="muted">· {person.roles.map(roleName).join(", ")}</span></li>
        {/each}
      </ul>
    {:else}
      <p class="muted">Nobody is assigned yet.</p>
    {/if}
  </section>
{/if}

<style>
  .people {
    margin: 0;
    padding: 0;
    border: 0;
  }
  .plain {
    margin: 0;
    padding-left: 1.2em;
  }
</style>
