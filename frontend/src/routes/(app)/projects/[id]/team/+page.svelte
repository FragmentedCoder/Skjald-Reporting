<script lang="ts">
  import BadgeCheck from "@lucide/svelte/icons/badge-check";
  import PenLine from "@lucide/svelte/icons/pen-line";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import RoleGroups, { ROLE_GROUPS } from "#lib/components/RoleGroups.svelte";
  import { sharedCustomer, sharedProject } from "#lib/context.js";
  import { reviewers, technicians, TEAM_ONLY, type ProjectDetail } from "#lib/customers.js";
  import { toast } from "#lib/toast.svelte.js";

  // Who works on the project, as what: technicians do the work, reviewers check it.
  // The responsible technician and the reviewer are chosen on Details; Managers and
  // Administrators add the others from the people assigned to the customer as
  // that. Someone who could be either is on the team as one of them only.
  const shared = sharedProject();
  const project = $derived(shared.current);
  const customer = $derived(sharedCustomer().current);
  const red = $derived(project?.classification === TEAM_ONLY);
  const fixed = $derived(new Set([project?.responsible?.id, project?.reviewer?.id]));
  const added = (role: string) =>
    (project?.team ?? []).filter((m) => !m.responsible && !m.reviewer && m.as_role === role).map((m) => m.id);
  // Start from the team now; the checkboxes change it until it's saved.
  let asTechnician = $derived(added("technician"));
  let asReviewer = $derived(added("reviewer"));
  let busy = $state(false);

  const sections = $derived([
    { role: "technician" as const, icon: PenLine, lead: project?.responsible,
      leadNote: "Responsible", missing: "No responsible technician yet: choose one on Details.",
      people: technicians(customer?.assigned ?? null).filter((p) => !fixed.has(p.id)) },
    { role: "reviewer" as const, icon: BadgeCheck, lead: project?.reviewer,
      leadNote: "The project's reviewer", missing: "No reviewer yet: choose one on Details.",
      people: reviewers(customer?.assigned ?? null).filter((p) => !fixed.has(p.id)) },
  ]);

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (!project) return;
    busy = true;
    try {
      shared.use(await api<ProjectDetail>("PUT", `/projects/${project.id}/team`,
        { technicians: asTechnician, reviewers: asReviewer }));
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
        This project is TLP:RED: only Managers, Administrators and the people on its team can
        see it.
      {:else}
        Who works on this project. Everyone assigned to {project.customer.name} can see it; if
        it's made TLP:RED, only its team, Managers and Administrators can.
      {/if}
      The responsible technician and the reviewer are chosen on Details.
    </p>
    {#if project.may_edit && customer}
      <form class="stack" onsubmit={save}>
        <div class="roles">
          {#each sections as section (section.role)}
            {@const about = ROLE_GROUPS[section.role]}
            <fieldset class="checks role {section.role}">
              <legend class="role-title">
                <section.icon size={16} aria-hidden="true" />{about.title}
              </legend>
              <p class="small muted">{about.about}</p>
              {#if section.lead}
                <label class="check">
                  <input type="checkbox" checked disabled />
                  <span>
                    <span class="check-title">{section.lead.name}</span>
                    <span class="small muted">{section.leadNote}</span>
                  </span>
                </label>
              {:else}
                <p class="small muted">{section.missing}</p>
              {/if}
              {#each section.people as person (person.id)}
                {@const other = section.role === "technician" ? asReviewer : asTechnician}
                {@const elsewhere = other.includes(person.id)}
                <label class="check">
                  {#if section.role === "technician"}
                    <input type="checkbox" value={person.id} bind:group={asTechnician} disabled={elsewhere} />
                  {:else}
                    <input type="checkbox" value={person.id} bind:group={asReviewer} disabled={elsewhere} />
                  {/if}
                  <span>
                    <span class="check-title">{person.display_name}</span>
                    {#if elsewhere}
                      <span class="small muted">
                        On the team as a {section.role === "technician" ? "reviewer" : "technician"}
                      </span>
                    {/if}
                  </span>
                </label>
              {/each}
            </fieldset>
          {/each}
        </div>
        <div><button class="button button-primary" type="submit" disabled={busy}>Save team</button></div>
      </form>
    {:else}
      <RoleGroups groups={[
        { role: "technician", empty: "Nobody yet.",
          people: project.team.filter((m) => m.as_role === "technician")
            .map((m) => ({ id: m.id, name: m.name, note: m.responsible ? "Responsible" : undefined })) },
        { role: "reviewer", empty: "Nobody yet.",
          people: project.team.filter((m) => m.as_role === "reviewer")
            .map((m) => ({ id: m.id, name: m.name, note: m.reviewer ? "The project's reviewer" : undefined })) },
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
