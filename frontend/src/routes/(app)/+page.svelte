<script lang="ts">
  import { onMount } from "svelte";
  import { api, sessionGone } from "#lib/api.js";
  import { branding } from "#lib/branding.svelte.js";
  import ProjectTable from "#lib/components/ProjectTable.svelte";
  import type { ProjectSummary } from "#lib/customers.js";
  import { roleName } from "#lib/roles.js";
  import { can, session } from "#lib/session.svelte.js";

  const info = $derived(session.current);
  let projects = $state<ProjectSummary[] | null>(null);

  // Yours first: the ones you're responsible for or review.
  const yours = (p: ProjectSummary) =>
    p.responsible?.id === info?.user.id || p.reviewer?.id === info?.user.id;
  const mine = $derived(projects?.filter(yours) ?? []);
  const others = $derived(projects?.filter((p) => !yours(p)) ?? []);

  onMount(async () => {
    try {
      projects = await api<ProjectSummary[]>("GET", "/projects");
    } catch (e) {
      if (!sessionGone(e)) projects = [];
    }
  });
</script>

<svelte:head><title>{branding.current.site_name}</title></svelte:head>

{#if info}
  <main class="page-content">
    <div class="heading">
      <h1 class="title">Welcome, {info.user.display_name}</h1>
      {#if info.user.roles.length}
        <p class="small muted">{info.user.roles.map(roleName).join(", ")}</p>
      {/if}
    </div>

    {#if projects?.length}
      {#if mine.length}
        <section class="section" aria-labelledby="mine-title">
          <h2 class="section-title" id="mine-title">Your projects</h2>
          <p class="small muted">Active projects you're responsible for or review.</p>
          <ProjectTable projects={mine} empty="" customer />
        </section>
      {/if}
      {#if others.length}
        <section class="section" aria-labelledby="others-title">
          <h2 class="section-title" id="others-title">
            {mine.length ? "Other active projects" : "Active projects"}
          </h2>
          <p class="small muted">For the customers you work with, newest first.</p>
          <ProjectTable projects={others} empty="" customer />
        </section>
      {/if}
    {:else if projects}
      <section class="empty">
        <p>No active projects yet.</p>
        <p class="small muted">
          {#if can(info, "manage_projects")}
            Add a customer, assign technicians and reviewers to it, and start its first project.
          {:else if info.user.roles.length}
            Projects for the customers you work with will appear here.
          {:else}
            You don't have a role yet. Ask an administrator for one.
          {/if}
        </p>
      </section>
    {/if}
  </main>
{/if}

<style>
  .heading {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .empty {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-8);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-lg);
    text-align: center;
  }
</style>
