<script lang="ts">
  import Plus from "@lucide/svelte/icons/plus";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import Dialog from "#lib/components/Dialog.svelte";
  import { sharedCustomer } from "#lib/context.js";
  import type { Contact, CustomerDetail, Site } from "#lib/customers.js";
  import { toast } from "#lib/toast.svelte.js";

  // The customer's people and places. Administrators change them; reports and
  // projects pick from them.
  const shared = sharedCustomer();
  const customer = $derived(shared.current);
  const base = $derived(`/customers/${customer?.id}`);

  let site = $state<{ id: number | null; name: string; address: string } | null>(null);
  let contact = $state<(Omit<Contact, "id"> & { id: number | null }) | null>(null);
  let siteOpen = $state(false);
  let contactOpen = $state(false);
  let error = $state<string | null>(null);
  let busy = $state(false);

  function editSite(found?: Site) {
    site = found ? { ...found } : { id: null, name: "", address: "" };
    error = null;
    siteOpen = true;
  }

  function editContact(found?: Contact) {
    contact = found ? { ...found } : { id: null, name: "", role: "", email: "", phone: "" };
    error = null;
    contactOpen = true;
  }

  async function run(action: () => Promise<CustomerDetail>, done: string, close?: () => void) {
    busy = true;
    error = null;
    try {
      shared.use(await action());
      close?.();
      toast(done, "ok", { key: "saved" });
    } catch (e) {
      if (sessionGone(e)) return;
      const message = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
      if (close) error = message;
      else toast(message, "critical");
    } finally {
      busy = false;
    }
  }

  function saveSite(event: SubmitEvent) {
    event.preventDefault();
    if (!site) return;
    const { id: siteId, ...body } = site;
    run(() => siteId === null
      ? api("POST", `${base}/sites`, body)
      : api("PUT", `${base}/sites/${siteId}`, body), "Site saved.", () => (siteOpen = false));
  }

  function saveContact(event: SubmitEvent) {
    event.preventDefault();
    if (!contact) return;
    const { id: contactId, ...body } = contact;
    run(() => contactId === null
      ? api("POST", `${base}/contacts`, body)
      : api("PUT", `${base}/contacts/${contactId}`, body), "Contact saved.",
    () => (contactOpen = false));
  }

  function remove(kind: "sites" | "contacts", itemId: number, name: string) {
    run(() => api("DELETE", `${base}/${kind}/${itemId}`), `${name} is removed.`);
  }
</script>

<svelte:head><title>{pageTitle(`Contacts & sites · ${customer?.name ?? "Customer"}`)}</title></svelte:head>

{#if customer}
  <section class="section" aria-labelledby="contacts-title">
    <div class="heading-row">
      <h2 class="section-title" id="contacts-title">Contacts</h2>
      {#if customer.may_manage}
        <button class="button button-secondary" type="button" onclick={() => editContact()}>
          <Plus size={16} aria-hidden="true" />Add contact
        </button>
      {/if}
    </div>
    <p class="small muted">
      People at the customer; a project names the one it's for. Encrypted with the customer's key.
    </p>
    {#if customer.contacts?.length}
      <ul class="cards">
        {#each customer.contacts as item (item.id)}
          <li>
            <p class="check-title">{item.name}</p>
            {#if item.role}<p class="small">{item.role}</p>{/if}
            <p class="small muted">{item.email || "No email"}{item.phone ? ` · ${item.phone}` : ""}</p>
            {#if customer.may_manage}
              <div class="row-actions">
                <button class="link-button" type="button" onclick={() => editContact(item)}>
                  Change<span class="visually-hidden"> {item.name}</span>
                </button>
                <button class="link-button" type="button" onclick={() => remove("contacts", item.id, item.name)}>
                  Remove<span class="visually-hidden"> {item.name}</span>
                </button>
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted">No contacts yet.</p>
    {/if}
  </section>

  <section class="section" aria-labelledby="sites-title">
    <div class="heading-row">
      <h2 class="section-title" id="sites-title">Sites</h2>
      {#if customer.may_manage}
        <button class="button button-secondary" type="button" onclick={() => editSite()}>
          <Plus size={16} aria-hidden="true" />Add site
        </button>
      {/if}
    </div>
    <p class="small muted">The customer's locations; a project names the ones it covers.</p>
    {#if customer.sites?.length}
      <ul class="cards">
        {#each customer.sites as item (item.id)}
          <li>
            <p class="check-title">{item.name}</p>
            <p class="small muted address">{item.address || "No address"}</p>
            {#if customer.may_manage}
              <div class="row-actions">
                <button class="link-button" type="button" onclick={() => editSite(item)}>
                  Change<span class="visually-hidden"> {item.name}</span>
                </button>
                <button class="link-button" type="button" onclick={() => remove("sites", item.id, item.name)}>
                  Remove<span class="visually-hidden"> {item.name}</span>
                </button>
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted">No sites yet.</p>
    {/if}
  </section>
{/if}

<Dialog bind:open={siteOpen} title={site?.id ? "Change site" : "Add site"}>
  {#if site}
    <form class="stack" onsubmit={saveSite}>
      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
      <div class="field">
        <label for="site-name">Name</label>
        <input id="site-name" class="input" required maxlength="150" bind:value={site.name} />
        <span class="hint">Such as “Head office” or “Datacentre Aarhus”.</span>
      </div>
      <div class="field">
        <label for="site-address">Address</label>
        <textarea id="site-address" class="input" rows="3" maxlength="500" bind:value={site.address}></textarea>
      </div>
      <div class="button-row end">
        <button class="button button-secondary" type="button" onclick={() => (siteOpen = false)}>Cancel</button>
        <button class="button button-primary" type="submit" disabled={busy}>Save site</button>
      </div>
    </form>
  {/if}
</Dialog>

<Dialog bind:open={contactOpen} title={contact?.id ? "Change contact" : "Add contact"}>
  {#if contact}
    <form class="stack" onsubmit={saveContact}>
      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}
      <div class="field">
        <label for="contact-name">Name</label>
        <input id="contact-name" class="input" required maxlength="200" bind:value={contact.name} />
      </div>
      <div class="field">
        <label for="contact-role">Role</label>
        <input id="contact-role" class="input" maxlength="150" bind:value={contact.role} />
        <span class="hint">Such as “IT manager”.</span>
      </div>
      <div class="field">
        <label for="contact-email">Email</label>
        <input id="contact-email" class="input" type="email" maxlength="254" bind:value={contact.email} />
      </div>
      <div class="field">
        <label for="contact-phone">Phone</label>
        <input id="contact-phone" class="input" type="tel" maxlength="50" bind:value={contact.phone} />
      </div>
      <div class="button-row end">
        <button class="button button-secondary" type="button" onclick={() => (contactOpen = false)}>Cancel</button>
        <button class="button button-primary" type="submit" disabled={busy}>Save contact</button>
      </div>
    </form>
  {/if}
</Dialog>

<style>
  .heading-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .cards li {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
  }
  .row-actions {
    display: flex;
    gap: var(--space-3);
    margin-top: var(--space-1);
  }
  .address {
    white-space: pre-line;
  }
  .end {
    justify-content: flex-end;
  }
</style>
