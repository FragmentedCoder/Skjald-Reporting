<script lang="ts">
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";
  import { api, sessionGone } from "#lib/api.js";
  import { branding } from "#lib/branding.svelte.js";
  import AppShell from "#lib/components/AppShell.svelte";
  import ProjectTable from "#lib/components/ProjectTable.svelte";
  import type { ProjectSummary } from "#lib/customers.js";
  import { roleName } from "#lib/roles.js";
  import { can, settle, type SessionInfo } from "#lib/session.svelte.js";

  let info = $state<SessionInfo | null>(null);
  let projects = $state<ProjectSummary[] | null>(null);

  // Yours first: the ones you're responsible for.
  const mine = $derived(projects?.filter((p) => p.responsible?.id === info?.user.id) ?? []);
  const others = $derived(projects?.filter((p) => p.responsible?.id !== info?.user.id) ?? []);

  onMount(async () => {
    info = await settle("app");
    if (!info) return;
    try {
      projects = await api<ProjectSummary[]>("GET", "/projects");
    } catch (e) {
      if (!sessionGone(e)) projects = [];
    }
  });
</script>

<svelte:head><title>{branding.current.site_name}</title></svelte:head>

{#if info}
  <AppShell {info}>
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
            <p class="small muted">Active projects you're responsible for.</p>
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
            {#if can(info, "manage_customers")}
              Add a customer, assign technicians to it, and start its first project.
            {:else if can(info, "create_projects_and_reports")}
              Start a project from one of <a href={resolve("/customers")}>your customers</a>.
            {:else if info.user.roles.length}
              Projects for the customers you work with will appear here.
            {:else}
              You don't have a role yet. Ask an administrator for one.
            {/if}
          </p>
        </section>
      {/if}
    </main>
  </AppShell>
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
