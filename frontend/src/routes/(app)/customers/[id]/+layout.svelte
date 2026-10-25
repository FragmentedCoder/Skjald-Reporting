<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import Building from "@lucide/svelte/icons/building";
  import type { Snippet } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { shareCustomer } from "#lib/context.js";
  import { formatCvr, LANGUAGES, type CustomerDetail } from "#lib/customers.js";
  import { chooseCustomer, refreshWorkspace } from "#lib/workspace.svelte.js";

  // A customer's pages share this: the customer (loaded once per customer), its
  // header, and the side menu opened on it.
  let { children }: { children: Snippet } = $props();

  let customer = $state<CustomerDetail | null>(null);
  let error = $state<string | null>(null);

  const id = $derived(page.params.id ?? "");

  async function load() {
    try {
      customer = await api<CustomerDetail>("GET", `/customers/${id}`);
      error = null;
    } catch (e) {
      customer = null;
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Not found.";
    }
  }

  shareCustomer({
    get current() {
      return customer;
    },
    use(found) {
      customer = found;
      void refreshWorkspace();
    },
    async reload() {
      await load();
      await refreshWorkspace();
    },
  });

  // Moving to another customer loads it and opens it in the menu.
  $effect(() => {
    const wanted = Number(id);
    void chooseCustomer(wanted);
    void load();
  });
</script>

<main class="page-content">
  {#if error}
    <div>
      <a class="small" href={resolve("/(app)/customers")}>All customers</a>
      <p class="alert alert-critical" role="alert">{error}</p>
    </div>
  {:else if customer}
    <header class="who">
      {#if customer.logo_url}
        <img class="logo" src={customer.logo_url} alt="" height="48" />
      {:else}
        <span class="logo-placeholder" aria-hidden="true"><Building size={24} /></span>
      {/if}
      <div>
        <p class="eyebrow small muted">Customer</p>
        <h1 class="title">{customer.name}</h1>
        {#if customer.visibility === "full"}
          <p class="small muted">
            CVR <span class="mono">{formatCvr(customer.cvr)}</span>
            · Reports in {LANGUAGES.find((l) => l.value === customer?.language)?.name}
          </p>
        {/if}
      </div>
    </header>

    {#if customer.visibility === "full"}
      {@render children()}
    {:else}
      <section class="section">
        <h2 class="section-title">
          {customer.visibility === "names" ? "Name only" : "Overview only"}
        </h2>
        <p class="muted">
          {#if customer.visibility === "names"}
            Report designers see every customer's name, to attach styles, but not its details or
            projects.
          {:else}
            Auditors see an overview of every customer: {customer.active_projects} active and
            {customer.archived_projects} archived projects. Details and projects are for the
            people assigned to it.
          {/if}
        </p>
      </section>
    {/if}
  {/if}
</main>

<style>
  .who {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }
  .eyebrow {
    font: var(--type-overline);
    letter-spacing: var(--type-overline-tracking);
    text-transform: uppercase;
  }
  .logo {
    width: auto;
    max-width: 160px;
    height: 48px;
    object-fit: contain;
  }
  .logo-placeholder {
    display: grid;
    flex: none;
    place-items: center;
    width: 48px;
    height: 48px;
    border-radius: var(--radius-md);
    background: var(--surface-subtle);
    color: var(--text-muted);
  }
</style>
