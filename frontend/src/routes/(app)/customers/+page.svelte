<script lang="ts">
  import { resolve } from "$app/paths";
  import Building from "@lucide/svelte/icons/building";
  import Plus from "@lucide/svelte/icons/plus";
  import Search from "@lucide/svelte/icons/search";
  import { onMount } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Pill from "#lib/components/Pill.svelte";
  import { formatCvr, LANGUAGES, type CustomerSummary } from "#lib/customers.js";
  import { date } from "#lib/format.js";
  import { can, session } from "#lib/session.svelte.js";

  // Every customer someone may see, with what they may see of it: for those with full
  // sight its logo, CVR, address and language, its projects, who works on it, its
  // contacts and sites, and when it was added; the totals above.

  const info = $derived(session.current);
  let customers = $state<CustomerSummary[] | null>(null);
  let query = $state("");
  let error = $state<string | null>(null);
  let searchTimer: ReturnType<typeof setTimeout> | undefined;

  const mayAdd = $derived(can(info, "manage_customers"));
  const limited = $derived(customers?.some((c) => c.visibility !== "full") ?? false);
  const full = $derived(customers?.filter((c) => c.visibility === "full") ?? []);
  const sum = (key: "active_projects" | "archived_projects") => (customers ?? []).reduce((n, c) => n + (c[key] ?? 0), 0);
  // For those who assign people: customers nobody can write a report for yet.
  const unstaffed = $derived(full.filter((c) => !c.technicians).length);

  const plural = (n: number | null, one: string, many = `${one}s`) => `${n ?? 0} ${n === 1 ? one : many}`;
  const languageName = (code: string | null) => LANGUAGES.find((l) => l.value === code)?.name ?? "—";

  async function load() {
    try {
      customers = await api<CustomerSummary[]>("GET", `/customers?q=${encodeURIComponent(query)}`);
      error = null;
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The customers could not be loaded.";
    }
  }

  // Searches as you type, once you pause.
  function search() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(load, 250);
  }

  onMount(load);
</script>

<svelte:head><title>{pageTitle("Customers")}</title></svelte:head>

<main class="page-content">
  <div class="page-header">
    <div>
      <h1 class="title">Customers</h1>
      <p class="small muted">
        {#if mayAdd}
          Every customer. Each has its own encryption key, so its details, contacts, projects
          and reports are sealed apart from the others'. Technicians and reviewers see only
          the customers they're assigned to: technicians write its reports, reviewers check and
          countersign them.
        {:else}
          The customers you work with. An administrator or manager assigns you to customers,
          as a technician, who writes their reports, or a reviewer, who checks and countersigns
          them.
        {/if}
      </p>
    </div>
    {#if mayAdd}
      <a class="button button-primary" href={resolve("/(app)/customers/new")}>
        <Plus size={18} aria-hidden="true" />
        Add customer
      </a>
    {/if}
  </div>

  <div class="field search">
    <label for="customer-search" class="visually-hidden">Search customers</label>
    <Search class="search-icon" size={16} aria-hidden="true" />
    <input id="customer-search" class="input" type="search" placeholder="Search by name or CVR"
      bind:value={query} oninput={search} />
  </div>

  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

  {#if customers}
    {#if customers.length}
      <ul class="totals" aria-label="Totals">
        <li><span class="figure">{customers.length}</span> <span class="small muted">{customers.length === 1 ? "customer" : "customers"}{query ? " found" : ""}</span></li>
        <li><span class="figure">{sum("active_projects")}</span> <span class="small muted">active projects</span></li>
        <li><span class="figure">{sum("archived_projects")}</span> <span class="small muted">archived projects</span></li>
        {#if mayAdd}
          <li class:warning={unstaffed > 0}>
            <span class="figure">{unstaffed}</span>
            <span class="small muted">{unstaffed === 1 ? "customer has" : "customers have"} no technician</span>
          </li>
        {/if}
      </ul>

      <div class="section table-wrap customers">
        <table class="table">
          <thead>
            <tr>
              <th>Customer</th><th>Projects</th><th>People</th><th class="roomy">Contacts and sites</th>
              <th class="roomy">Report language</th><th class="roomy">Added</th>
            </tr>
          </thead>
          <tbody>
            {#each customers as customer (customer.id)}
              {@const seen = customer.visibility === "full"}
              <tr>
                <td>
                  <div class="who">
                    <span class="logo" aria-hidden="true">
                      {#if customer.logo_url}<img src={customer.logo_url} alt="" />{:else}<Building size={18} />{/if}
                    </span>
                    <div class="who-text">
                      <a class="row-link" href={resolve("/(app)/customers/[id]", { id: String(customer.id) })}>
                        {customer.name}
                      </a>
                      {#if customer.visibility !== "full"}
                        <Pill tone="neutral"
                          text={customer.visibility === "names" ? "Name only" : "Overview only"} />
                      {/if}
                      {#if seen}
                        <span class="small muted line" title={customer.address ?? undefined}>
                          {[customer.cvr ? `CVR ${formatCvr(customer.cvr)}` : "", customer.address ?? ""].filter(Boolean).join(" · ") || "No CVR or address yet"}
                        </span>
                      {/if}
                    </div>
                  </div>
                </td>
                <td>
                  {#if customer.active_projects === null}—{:else}
                    {customer.active_projects} active
                    <span class="small muted block">{customer.archived_projects} archived</span>
                  {/if}
                </td>
                <td>
                  {#if !seen}—{:else}
                    {plural(customer.technicians, "technician")}
                    <span class="small muted block">{plural(customer.reviewers, "reviewer")}</span>
                    {#if mayAdd && !customer.technicians}<Pill tone="warning" text="No technician" />{/if}
                  {/if}
                </td>
                <td class="roomy">
                  {#if !seen}—{:else}
                    {plural(customer.contacts_count, "contact")}
                    <span class="small muted block">{plural(customer.sites_count, "site")}</span>
                  {/if}
                </td>
                <td class="roomy">{seen ? languageName(customer.language) : "—"}</td>
                <td class="roomy">{seen ? date(customer.created_at) : "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="small muted">
        People are those assigned to the customer; someone holding both roles can be its technician and its reviewer.
        Projects count only those you may open.
      </p>
      {#if limited}
        <p class="small muted">
          Your role shows some customers by name or overview only: enough to attach styles or
          audit, without their contacts or projects.
        </p>
      {/if}
    {:else}
      <section class="empty">
        <p>{query ? "No customer matches that." : "No customers yet."}</p>
        <p class="small muted">
          {#if query}
            Try part of the name, or the CVR number.
          {:else if mayAdd}
            Add the first one, with its sites and contacts.
          {:else}
            An administrator assigns you to the customers you work with.
          {/if}
        </p>
      </section>
    {/if}
  {/if}
</main>

<style>
  /* The totals of the customers listed, side by side where they fit. */
  .totals {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .totals li {
    display: grid;
    gap: 2px;
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .totals li.warning {
    border-color: transparent;
    background: var(--warning-bg);
  }
  .figure {
    font-size: 24px;
    font-weight: 600;
    line-height: 1.2;
  }
  .warning .figure {
    color: var(--warning-text);
  }
  /* Where the table is narrow, as on a phone, the extra columns go. */
  .customers {
    container-type: inline-size;
  }
  @container (max-width: 760px) {
    .roomy {
      display: none;
    }
  }
  .who {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    min-width: 0;
  }
  .logo {
    display: grid;
    flex: none;
    place-items: center;
    width: 36px;
    height: 36px;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface-subtle);
    color: var(--text-muted);
  }
  .logo img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .who-text {
    display: grid;
    justify-items: start;
    gap: 2px;
    min-width: 0;
  }
  .line {
    max-width: 420px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .block {
    display: block;
  }
  .search {
    position: relative;
    max-width: 420px;
  }
  .search :global(.search-icon) {
    position: absolute;
    top: 50%;
    left: 12px;
    color: var(--text-muted);
    transform: translateY(-50%);
  }
  .search .input {
    padding-left: 36px;
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
