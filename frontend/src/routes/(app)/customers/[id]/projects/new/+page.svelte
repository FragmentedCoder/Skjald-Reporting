<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import ProjectFields, { projectBody, type ProjectForm } from "#lib/components/ProjectFields.svelte";
  import { sharedCustomer } from "#lib/context.js";
  import { DEFAULT_CLASSIFICATION, type ProjectDetail } from "#lib/customers.js";
  import { session } from "#lib/session.svelte.js";
  import { toast } from "#lib/toast.svelte.js";
  import { refreshWorkspace } from "#lib/workspace.svelte.js";

  const shared = sharedCustomer();
  const customer = $derived(shared.current);
  const id = $derived(String(customer?.id ?? ""));
  let form = $state<ProjectForm>({
    name: "", start_date: "", end_date: "", responsible_id: "", contact_id: "", site_ids: [],
    classification: DEFAULT_CLASSIFICATION,
  });
  let error = $state<string | null>(null);
  let busy = $state(false);
  let guessed = false;

  // The person creating it is the likely one responsible, if they can be.
  $effect(() => {
    if (guessed || !customer) return;
    guessed = true;
    const me = customer.assigned?.find((p) => p.id === session.current?.user.id && p.roles.includes("technician"));
    if (me) form.responsible_id = String(me.id);
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      const created = await api<ProjectDetail>("POST", `/customers/${id}/projects`, projectBody(form));
      toast(`${created.number} is created.`, "ok");
      await refreshWorkspace();
      await goto(resolve("/(app)/projects/[id]", { id: String(created.id) }));
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The project could not be created.";
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{pageTitle(`New project · ${customer?.name ?? "Customer"}`)}</title></svelte:head>

{#if customer}
  <section class="section" aria-labelledby="new-title">
    <h2 class="section-title" id="new-title">New project</h2>
    <p class="small muted">It gets its number when you create it.</p>
    {#if customer.may_create_projects}
      <form class="stack form-wide" onsubmit={submit}>
        {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
        <ProjectFields bind:values={form} {customer} />
        <div class="button-row">
          <button class="button button-primary" type="submit" disabled={busy}>Create project</button>
          <a class="button button-secondary" href={resolve("/(app)/customers/[id]/projects", { id })}>Cancel</a>
        </div>
      </form>
    {:else}
      <p class="alert alert-warning">
        Only administrators and the technicians assigned to {customer.name} create its projects.
      </p>
    {/if}
  </section>
{/if}

<style>
  .form-wide {
    max-width: 680px;
  }
</style>
