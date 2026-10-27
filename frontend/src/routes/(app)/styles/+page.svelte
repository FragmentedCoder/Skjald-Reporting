<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Plus from "@lucide/svelte/icons/plus";
  import Star from "@lucide/svelte/icons/star";
  import StarOff from "@lucide/svelte/icons/star-off";
  import X from "@lucide/svelte/icons/x";
  import { onMount } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import RowMenu, { type MenuItem } from "#lib/components/RowMenu.svelte";
  import type { CustomerSummary } from "#lib/customers.js";
  import { dateTime } from "#lib/format.js";
  import { stylesApi, type StyleSummary } from "#lib/reportStyles/api.js";
  import { toast } from "#lib/toast.svelte.js";

  // Report styles: the company's, stacked on the Skjald default, and customers' own,
  // stacked on one of the company's. A technician picks among those a customer allows.
  let styles = $state<StyleSummary[] | null>(null);
  let error = $state<string | null>(null);
  const company = $derived((styles ?? []).filter((s) => s.customer_id === null));
  const byCustomer = $derived.by(() => {
    const groups: { id: number; name: string; styles: StyleSummary[] }[] = [];
    for (const s of styles ?? []) {
      if (s.customer_id === null) continue;
      let group = groups.find((g) => g.id === s.customer_id);
      if (!group) groups.push((group = { id: s.customer_id, name: s.customer_name ?? `Customer ${s.customer_id}`, styles: [] }));
      group.styles.push(s);
    }
    return groups;
  });

  async function load() {
    try {
      styles = await stylesApi.list();
      error = null;
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "The styles could not be loaded.";
    }
  }
  onMount(load);

  // A new style
  let adding = $state(false);
  let name = $state("");
  let owner = $state("company");
  let basedOn = $state("");
  let customers = $state<CustomerSummary[]>([]);
  let busy = $state(false);

  async function startAdding() {
    name = "";
    owner = "company";
    basedOn = String(company.find((s) => s.is_default)?.id ?? "");
    adding = true;
    try {
      customers = (await api<CustomerSummary[]>("GET", "/customers")).filter((c) => c.name);
    } catch {
      customers = [];
    }
  }

  async function add(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    try {
      const customerId = owner === "company" ? null : Number(owner);
      const made = await stylesApi.create(name, customerId, customerId !== null && basedOn ? Number(basedOn) : null);
      adding = false;
      await goto(resolve("/(app)/styles/[id]", { id: String(made.id) }));
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The style couldn't be made.", "critical");
    } finally {
      busy = false;
    }
  }

  async function act(run: () => Promise<unknown>, done: string) {
    try {
      await run();
      toast(done, "ok");
      await load();
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "That didn't work. Try again.", "critical");
    }
  }

  function menu(style: StyleSummary): MenuItem[] {
    const items: MenuItem[] = [{ label: "Change", icon: Pencil, run: () => void goto(resolve("/(app)/styles/[id]", { id: String(style.id) })) }];
    if (style.customer_id === null) {
      items.push(style.is_default
        ? { label: "Stop using as the default", icon: StarOff, run: () => void act(() => stylesApi.setCompanyDefault(null), "Reports now use the Skjald default unless a customer's choice says otherwise.") }
        : { label: "Make the company default", icon: Star, run: () => void act(() => stylesApi.setCompanyDefault(style.id), `Reports now use ${style.name} unless a customer's choice says otherwise.`) });
    }
    items.push({ label: "Remove", icon: X, danger: true, run: () => void act(() => stylesApi.remove(style.id), `${style.name} is removed. Its history is kept.`) });
    return items;
  }
</script>

<svelte:head><title>{pageTitle("Styles")}</title></svelte:head>

<main class="page-content">
  <div class="page-header">
    <div>
      <h1 class="title">Styles</h1>
      <p class="small muted">How reports look: colours, fonts, margins, and what goes on the cover and around each page. A style changes only what it needs to from the one it stacks on.</p>
    </div>
    <button class="button button-primary" type="button" onclick={startAdding}>
      <Plus size={18} aria-hidden="true" /> New style
    </button>
  </div>

  {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

  {#if styles}
    <section class="section">
      <h2 class="section-title">The company's styles</h2>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Name</th><th class="roomy">Changed</th><th><span class="visually-hidden">Actions</span></th></tr></thead>
          <tbody>
            <tr>
              <td>The Skjald default {#if !company.some((s) => s.is_default)}<Pill tone="ok" text="Company default" />{/if}
                <span class="small muted block">Ships with Skjald, and every style stacks on it. It can't be changed.</span></td>
              <td class="roomy small muted">—</td>
              <td></td>
            </tr>
            {#each company as style (style.id)}
              <tr>
                <td><a href={resolve("/(app)/styles/[id]", { id: String(style.id) })}>{style.name}</a>
                  {#if style.is_default}<Pill tone="ok" text="Company default" />{/if}</td>
                <td class="roomy small">{style.updated_by ?? "Someone"}, {dateTime(style.updated_at)}<span class="muted"> · version {style.version}</span></td>
                <td class="actions"><RowMenu label="Actions for {style.name}" items={menu(style)} /></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">Customers' styles</h2>
      {#if byCustomer.length}
        {#each byCustomer as group (group.id)}
          <h3 class="customer">{group.name}</h3>
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>Name</th><th>Stacks on</th><th class="roomy">Changed</th><th><span class="visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {#each group.styles as style (style.id)}
                  <tr>
                    <td><a href={resolve("/(app)/styles/[id]", { id: String(style.id) })}>{style.name}</a></td>
                    <td class="small">{company.find((c) => c.id === style.based_on)?.name ?? "The Skjald default"}</td>
                    <td class="roomy small">{style.updated_by ?? "Someone"}, {dateTime(style.updated_at)}<span class="muted"> · version {style.version}</span></td>
                    <td class="actions"><RowMenu label="Actions for {style.name}" items={menu(style)} /></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/each}
      {:else}
        <p class="small muted">None yet. A customer who wants reports in their own look gets a style of their own; one with a letterhead can have it as a report background in the customer's settings.</p>
      {/if}
    </section>
  {:else if !error}
    <p class="muted">Loading…</p>
  {/if}
</main>

<Dialog bind:open={adding} title="New style">
  <form id="new-style" class="stack" onsubmit={add}>
    <div class="field">
      <label for="style-name">Name</label>
      <input id="style-name" class="input" bind:value={name} required maxlength="100" />
    </div>
    <div class="field">
      <label for="style-owner">For</label>
      <select id="style-owner" class="input" bind:value={owner}>
        <option value="company">The company</option>
        {#each customers as c (c.id)}<option value={String(c.id)}>{c.name}</option>{/each}
      </select>
      <span class="hint">A customer's style is sealed with the customer's key, and goes if the customer is deleted.</span>
    </div>
    {#if owner !== "company"}
      <div class="field">
        <label for="style-base">Stacks on</label>
        <select id="style-base" class="input" bind:value={basedOn}>
          <option value="">The Skjald default</option>
          {#each company as s (s.id)}<option value={String(s.id)}>{s.name}</option>{/each}
        </select>
      </div>
    {/if}
  </form>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (adding = false)}>Cancel</button>
    <button class="button button-primary" type="submit" form="new-style" disabled={busy}>Make the style</button>
  {/snippet}
</Dialog>

<style>
  .customer {
    margin: var(--space-4) 0 var(--space-2);
    font-size: 1rem;
    font-weight: 600;
  }
  .block {
    display: block;
  }
  .actions {
    width: 1%;
    white-space: nowrap;
  }
</style>
