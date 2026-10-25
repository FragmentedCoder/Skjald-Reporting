<script lang="ts">
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Pill from "#lib/components/Pill.svelte";
  import { sharedCustomer, sharedProject } from "#lib/context.js";
  import { TEAM_ONLY, type ProjectDetail } from "#lib/customers.js";
  import { roleName } from "#lib/roles.js";
  import { toast } from "#lib/toast.svelte.js";

  // Who works on the project. Its responsible technician always does; the others
  // are picked from the people assigned to the customer.
  const shared = sharedProject();
  const project = $derived(shared.current);
  const customer = $derived(sharedCustomer().current);
  const red = $derived(project?.classification === TEAM_ONLY);
  // Starts from the team now (its responsible included); the checkboxes change it.
  let chosen = $derived((project?.team ?? []).map((m) => m.id));
  let busy = $state(false);

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!project) return;
    busy = true;
    try {
      shared.use(await api<ProjectDetail>("PUT", `/projects/${project.id}/team`, { user_ids: chosen }));
      toast("The team is saved.", "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "Something went wrong.", "critical");
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{pageTitle(project ? `Team · ${project.number}` : "Project")}</title></svelte:head>

{#if project}
  <section class="section" aria-labelledby="team-title">
    <h2 class="section-title" id="team-title">Team</h2>
    <p class="small muted">
      {#if red}
        This project is TLP:RED: only administrators and the people on its team can see it.
      {:else}
        Who works on this project. Everyone assigned to {project.customer.name} can see it; if
        it's made TLP:RED, only its team and administrators can.
      {/if}
    </p>
    {#if project.may_edit && customer}
      <form class="stack" onsubmit={save}>
        {#if customer.assigned?.length}
          <fieldset class="checks people">
            <legend class="visually-hidden">Team members</legend>
            {#each customer.assigned as person (person.id)}
              {@const responsible = person.id === project.responsible?.id}
              <label class="check">
                <input type="checkbox" value={person.id} bind:group={chosen} disabled={responsible} />
                <span>
                  <span class="check-title">{person.display_name}</span>
                  <span class="small muted">
                    {responsible ? "Responsible · " : ""}{person.roles.map(roleName).join(", ")}
                  </span>
                </span>
              </label>
            {/each}
          </fieldset>
          <div><button class="button button-primary" type="submit" disabled={busy}>Save team</button></div>
        {:else}
          <p class="muted">Nobody is assigned to {project.customer.name} yet. Assign people on the customer first.</p>
        {/if}
      </form>
    {:else if project.team.length}
      <ul class="members">
        {#each project.team as member (member.id)}
          <li>
            <span class="check-title">{member.name}</span>
            <span class="small muted">{member.roles.map(roleName).join(", ")}</span>
            {#if member.responsible}<Pill tone="info" text="Responsible" />{/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted">Nobody is on the team yet.</p>
    {/if}
  </section>
{/if}

<style>
  .people {
    margin: 0;
    padding: 0;
    border: 0;
  }
  .members {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .members li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }
</style>
