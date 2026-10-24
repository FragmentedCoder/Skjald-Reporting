<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { onMount } from "svelte";
  import { api, ApiError } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import AppShell from "#lib/components/AppShell.svelte";
  import CustomerFields from "#lib/components/CustomerFields.svelte";
  import { type CustomerDetail } from "#lib/customers.js";
  import { can, settle, type SessionInfo } from "#lib/session.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  let info = $state<SessionInfo | null>(null);
  let form = $state({ name: "", cvr: "", address: "", language: "da", retention_months: 12 });
  let error = $state<string | null>(null);
  let busy = $state(false);

  onMount(async () => {
    info = await settle("app");
    if (info && !can(info, "manage_customers")) await goto(resolve("/customers"), { replace: true });
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      const created = await api<CustomerDetail>("POST", "/customers", form);
      toast(`${created.name} is added, with its own encryption key.`, "ok");
      await goto(resolve("/customers/[id]", { id: String(created.id) }));
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The customer could not be added.";
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{pageTitle("Add customer")}</title></svelte:head>

{#if info}
  <AppShell {info}>
    <main class="page-content">
      <div class="page-header">
        <div>
          <a class="small" href={resolve("/customers")}>Customers</a>
          <h1 class="title">Add customer</h1>
          <p class="small muted">
            Sites, contacts and who works with the customer come next, on its page.
          </p>
        </div>
      </div>
      <form class="section stack form-wide" onsubmit={submit}>
        {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
        <CustomerFields bind:values={form} />
        <div class="button-row">
          <button class="button button-primary" type="submit" disabled={busy}>Add customer</button>
          <a class="button button-secondary" href={resolve("/customers")}>Cancel</a>
        </div>
      </form>
    </main>
  </AppShell>
{/if}

<style>
  .form-wide {
    max-width: 640px;
  }
</style>
