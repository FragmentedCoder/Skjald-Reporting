<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { onMount } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import AppShell from "#lib/components/AppShell.svelte";
  import ProjectFields, { projectBody, type ProjectForm } from "#lib/components/ProjectFields.svelte";
  import { DEFAULT_CLASSIFICATION, type CustomerDetail, type ProjectDetail } from "#lib/customers.js";
  import { settle, type SessionInfo } from "#lib/session.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  let info = $state<SessionInfo | null>(null);
  let customer = $state<CustomerDetail | null>(null);
  let form = $state<ProjectForm>({
    name: "", start_date: "", end_date: "", responsible_id: "", contact_id: "", site_ids: [],
    classification: DEFAULT_CLASSIFICATION,
  });
  let error = $state<string | null>(null);
  let busy = $state(false);

  const id = $derived(page.params.id ?? "");

  onMount(async () => {
    info = await settle("app");
    if (!info) return;
    try {
      customer = await api<CustomerDetail>("GET", `/customers/${id}`);
      // The person creating it is the likely one responsible, if they can be.
      const me = customer.assigned?.find((p) => p.id === info?.user.id && p.roles.includes("technician"));
      if (me) form.responsible_id = String(me.id);
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Not found.";
    }
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      const created = await api<ProjectDetail>("POST", `/customers/${id}/projects`, projectBody(form));
      toast(`${created.number} is created.`, "ok");
      await goto(resolve("/projects/[id]", { id: String(created.id) }));
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The project could not be created.";
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{pageTitle("New project")}</title></svelte:head>

{#if info}
  <AppShell {info}>
    <main class="page-content">
      <div class="page-header">
        <div>
          {#if customer}
            <a class="small" href={resolve("/customers/[id]", { id })}>{customer.name}</a>
          {/if}
          <h1 class="title">New project</h1>
          <p class="small muted">It gets its number when you create it.</p>
        </div>
      </div>
      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
      {#if customer}
        {#if customer.may_create_projects}
          <form class="section stack form-wide" onsubmit={submit}>
            <ProjectFields bind:values={form} {customer} />
            <div class="button-row">
              <button class="button button-primary" type="submit" disabled={busy}>Create project</button>
              <a class="button button-secondary" href={resolve("/customers/[id]", { id })}>Cancel</a>
            </div>
          </form>
        {:else}
          <p class="alert alert-warning">
            Only administrators and the technicians assigned to {customer.name} create its projects.
          </p>
        {/if}
      {/if}
    </main>
  </AppShell>
{/if}

<style>
  .form-wide {
    max-width: 680px;
  }
</style>
