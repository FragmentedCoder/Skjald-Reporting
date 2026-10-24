<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import Building from "@lucide/svelte/icons/building";
  import ImageIcon from "@lucide/svelte/icons/image";
  import Plus from "@lucide/svelte/icons/plus";
  import { onMount } from "svelte";
  import { api, ApiError, sessionGone } from "#lib/api.js";
  import { pageTitle } from "#lib/branding.svelte.js";
  import AppShell from "#lib/components/AppShell.svelte";
  import CustomerFields from "#lib/components/CustomerFields.svelte";
  import Dialog from "#lib/components/Dialog.svelte";
  import Pill from "#lib/components/Pill.svelte";
  import ProjectTable from "#lib/components/ProjectTable.svelte";
  import {
    formatCvr,
    LANGUAGES,
    type Contact,
    type CustomerDetail,
    type ProjectSummary,
    type Site,
  } from "#lib/customers.js";
  import { dateTime } from "#lib/format.js";
  import { roleName } from "#lib/roles.js";
  import { settle, type SessionInfo } from "#lib/session.svelte.js";
  import { withStepUp } from "#lib/stepUp.svelte.js";
  import { toast } from "#lib/toast.svelte.js";

  type Tab = "projects" | "archived" | "details" | "people";

  let info = $state<SessionInfo | null>(null);
  let customer = $state<CustomerDetail | null>(null);
  let projects = $state<ProjectSummary[] | null>(null);
  let archived = $state<ProjectSummary[] | null>(null);
  let tab = $state<Tab>("projects");
  let error = $state<string | null>(null);
  let busy = $state(false);

  let details = $state({ name: "", cvr: "", address: "", language: "da", retention_months: 12 });
  let people = $state<number[]>([]);
  let logoInput = $state<HTMLInputElement>();

  // Adding or changing a site or a contact happens in a dialog.
  let site = $state<{ id: number | null; name: string; address: string } | null>(null);
  let contact = $state<(Omit<Contact, "id"> & { id: number | null }) | null>(null);
  let siteOpen = $state(false);
  let contactOpen = $state(false);
  let dialogError = $state<string | null>(null);

  let deleteOpen = $state(false);
  let deleteName = $state("");

  const id = $derived(page.params.id ?? "");
  const tabs = $derived<{ key: Tab; label: string }[]>([
    { key: "projects", label: `Projects (${customer?.active_projects ?? 0})` },
    { key: "archived", label: `Archived (${customer?.archived_projects ?? 0})` },
    { key: "details", label: "Details" },
    { key: "people", label: `People (${customer?.assigned?.length ?? 0})` },
  ]);

  function use(found: CustomerDetail) {
    customer = found;
    details = {
      name: found.name,
      cvr: found.cvr ?? "",
      address: found.address ?? "",
      language: found.language ?? "da",
      retention_months: found.retention_months ?? 12,
    };
    people = (found.assigned ?? []).map((p) => p.id);
  }

  async function load() {
    use(await api<CustomerDetail>("GET", `/customers/${id}`));
    if (customer?.visibility === "full") {
      projects = await api<ProjectSummary[]>("GET", `/customers/${id}/projects`);
    }
  }

  onMount(async () => {
    info = await settle("app");
    if (!info) return;
    try {
      await load();
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Not found.";
    }
  });

  async function show(next: Tab) {
    tab = next;
    if (next === "archived" && archived === null) {
      archived = await api<ProjectSummary[]>("GET", `/customers/${id}/projects?archived=true`);
    }
  }

  async function run(action: () => Promise<void>, done?: string) {
    busy = true;
    error = null;
    try {
      await action();
      if (done) toast(done, "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) error = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
    } finally {
      busy = false;
    }
  }

  function saveDetails(event: SubmitEvent) {
    event.preventDefault();
    run(async () => use(await api<CustomerDetail>("PATCH", `/customers/${id}`, details)), "Details saved.");
  }

  function savePeople(event: SubmitEvent) {
    event.preventDefault();
    run(async () => {
      use(await api<CustomerDetail>("PUT", `/customers/${id}/assignments`, { user_ids: people }));
    }, "Who works with this customer is saved.");
  }

  function uploadLogo() {
    const file = logoInput?.files?.[0];
    if (logoInput) logoInput.value = "";
    if (!file) return;
    run(async () => use(await api<CustomerDetail>("PUT", `/customers/${id}/logo`, file)), "Logo saved.");
  }

  function editSite(found?: Site) {
    site = found ? { ...found } : { id: null, name: "", address: "" };
    dialogError = null;
    siteOpen = true;
  }

  function editContact(found?: Contact) {
    contact = found ? { ...found } : { id: null, name: "", role: "", email: "", phone: "" };
    dialogError = null;
    contactOpen = true;
  }

  async function inDialog(action: () => Promise<CustomerDetail>, close: () => void, done: string) {
    busy = true;
    dialogError = null;
    try {
      use(await action());
      close();
      toast(done, "ok", { key: "saved" });
    } catch (e) {
      if (!sessionGone(e)) dialogError = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
    } finally {
      busy = false;
    }
  }

  function saveSite(event: SubmitEvent) {
    event.preventDefault();
    if (!site) return;
    const { id: siteId, ...body } = site;
    inDialog(
      () => siteId === null
        ? api("POST", `/customers/${id}/sites`, body)
        : api("PUT", `/customers/${id}/sites/${siteId}`, body),
      () => (siteOpen = false),
      "Site saved.",
    );
  }

  function saveContact(event: SubmitEvent) {
    event.preventDefault();
    if (!contact) return;
    const { id: contactId, ...body } = contact;
    inDialog(
      () => contactId === null
        ? api("POST", `/customers/${id}/contacts`, body)
        : api("PUT", `/customers/${id}/contacts/${contactId}`, body),
      () => (contactOpen = false),
      "Contact saved.",
    );
  }

  function remove(kind: "sites" | "contacts", itemId: number, name: string) {
    run(async () => use(await api<CustomerDetail>("DELETE", `/customers/${id}/${kind}/${itemId}`)),
      `${name} is removed.`);
  }

  async function deleteCustomer(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    dialogError = null;
    try {
      await withStepUp(() => api("DELETE", `/customers/${id}`, { confirm_name: deleteName }));
      toast(`${customer?.name} is deleted, and its key with it.`, "ok");
      await goto(resolve("/customers"));
    } catch (e) {
      if (e instanceof ApiError && e.reason === "step_up_cancelled") return;
      if (!sessionGone(e)) dialogError = e instanceof ApiError ? e.message : "The customer could not be deleted.";
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><title>{pageTitle(customer?.name ?? "Customer")}</title></svelte:head>

{#if info}
  <AppShell {info}>
    <main class="page-content">
      <div class="page-header">
        <div>
          <a class="small" href={resolve("/customers")}>Customers</a>
          <div class="who">
            {#if customer?.logo_url}
              <img class="logo" src={customer.logo_url} alt="" height="48" />
            {:else}
              <span class="logo-placeholder" aria-hidden="true"><Building size={24} /></span>
            {/if}
            <div>
              <h1 class="title">{customer?.name ?? "Customer"}</h1>
              {#if customer?.visibility === "full"}
                <p class="small muted">
                  CVR <span class="mono">{formatCvr(customer.cvr)}</span>
                  · Reports in {LANGUAGES.find((l) => l.value === customer?.language)?.name}
                </p>
              {/if}
            </div>
          </div>
        </div>
        {#if customer?.may_create_projects && tab === "projects"}
          <a class="button button-primary" href={resolve("/customers/[id]/projects/new", { id })}>
            <Plus size={18} aria-hidden="true" />
            New project
          </a>
        {/if}
      </div>

      {#if error}<p class="alert alert-critical" role="alert">{error}</p>{/if}

      {#if customer && customer.visibility !== "full"}
        <section class="section">
          <h2 class="section-title">
            {customer.visibility === "names" ? "Name only" : "Overview only"}
          </h2>
          <p class="muted">
            {#if customer.visibility === "names"}
              Report designers see every customer's name, to attach styles, but not its details
              or projects.
            {:else}
              Auditors see an overview of every customer: {customer.active_projects} active and
              {customer.archived_projects} archived projects. Details and projects are for the
              people assigned to it.
            {/if}
          </p>
        </section>
      {:else if customer}
        <div class="tabs" role="tablist" aria-label="Customer">
          {#each tabs as item (item.key)}
            <button type="button" role="tab" id="tab-{item.key}" aria-controls="panel-{item.key}"
              aria-selected={tab === item.key} tabindex={tab === item.key ? 0 : -1}
              onclick={() => show(item.key)}>{item.label}</button>
          {/each}
        </div>

        <div role="tabpanel" id="panel-{tab}" aria-labelledby="tab-{tab}" class="stack">
          {#if tab === "projects"}
            <section class="section">
              <p class="small muted">
                The work under way for this customer. Archive a project when it's done: it and its
                reports become read-only, and retention counts from then.
              </p>
              <ProjectTable projects={projects ?? []}
                empty={customer.may_create_projects
                  ? "No active projects. Start one with New project."
                  : "No active projects."} />
            </section>
          {:else if tab === "archived"}
            <section class="section">
              <p class="small muted">
                Finished projects: read-only, with their reports. An administrator can reopen one.
              </p>
              <ProjectTable projects={archived ?? []} empty="Nothing archived yet." />
            </section>
          {:else if tab === "details"}
            <section class="section" aria-labelledby="details-title">
              <h2 class="section-title" id="details-title">Details</h2>
              <p class="small muted">
                Reports fill these in for you. The address and contacts are encrypted with this
                customer's own key.
              </p>
              {#if customer.may_manage}
                <form class="stack form-wide" onsubmit={saveDetails}>
                  <CustomerFields bind:values={details} />
                  <div><button class="button button-primary" type="submit" disabled={busy}>Save details</button></div>
                </form>
              {:else}
                <dl class="facts">
                  <dt>Address</dt>
                  <dd class="address">{customer.address || "—"}</dd>
                  <dt>Report language</dt>
                  <dd>{LANGUAGES.find((l) => l.value === customer?.language)?.name}</dd>
                  <dt>Raw data kept</dt>
                  <dd>{customer.retention_months} months after a project is archived</dd>
                  <dt>Added</dt>
                  <dd>{dateTime(customer.created_at)}</dd>
                </dl>
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
                          <button class="link-button" type="button"
                            onclick={() => remove("sites", item.id, item.name)}>
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

            <section class="section" aria-labelledby="contacts-title">
              <div class="heading-row">
                <h2 class="section-title" id="contacts-title">Contacts</h2>
                {#if customer.may_manage}
                  <button class="button button-secondary" type="button" onclick={() => editContact()}>
                    <Plus size={16} aria-hidden="true" />Add contact
                  </button>
                {/if}
              </div>
              <p class="small muted">People at the customer; a project names the one it's for.</p>
              {#if customer.contacts?.length}
                <ul class="cards">
                  {#each customer.contacts as item (item.id)}
                    <li>
                      <p class="check-title">{item.name}</p>
                      {#if item.role}<p class="small">{item.role}</p>{/if}
                      <p class="small muted">
                        {item.email || "No email"}{item.phone ? ` · ${item.phone}` : ""}
                      </p>
                      {#if customer.may_manage}
                        <div class="row-actions">
                          <button class="link-button" type="button" onclick={() => editContact(item)}>
                            Change<span class="visually-hidden"> {item.name}</span>
                          </button>
                          <button class="link-button" type="button"
                            onclick={() => remove("contacts", item.id, item.name)}>
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

            {#if customer.may_manage}
              <section class="section" aria-labelledby="logo-title">
                <h2 class="section-title" id="logo-title">Logo</h2>
                <p class="small muted">
                  For reports in the customer's own style. A PNG, JPEG, WebP or GIF up to 2 MB.
                </p>
                <input bind:this={logoInput} class="visually-hidden" type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif" onchange={uploadLogo} />
                <div class="button-row">
                  <button class="button button-secondary" type="button" disabled={busy}
                    onclick={() => logoInput?.click()}>
                    <ImageIcon size={16} aria-hidden="true" />
                    {customer.logo_url ? "Replace logo" : "Upload a logo"}
                  </button>
                  {#if customer.logo_url}
                    <button class="button button-secondary" type="button" disabled={busy}
                      onclick={() => run(async () => use(await api("DELETE", `/customers/${id}/logo`)), "Logo removed.")}>
                      Remove logo
                    </button>
                  {/if}
                </div>
              </section>

              <section class="section danger-zone" aria-labelledby="delete-title">
                <h2 class="section-title" id="delete-title">Delete customer</h2>
                <p class="small">
                  Deletes the customer, its sites, contacts and projects, and its encryption key:
                  whatever was encrypted with it can't be read again. This can't be undone.
                </p>
                <div>
                  <button class="button button-secondary danger" type="button"
                    onclick={() => { deleteName = ""; dialogError = null; deleteOpen = true; }}>
                    Delete customer
                  </button>
                </div>
              </section>
            {/if}
          {:else if tab === "people"}
            <section class="section" aria-labelledby="people-title">
              <h2 class="section-title" id="people-title">Who works with this customer</h2>
              <p class="small muted">
                Technicians and reviewers see only the customers they're assigned to. Technicians
                create projects and reports for them; reviewers review and countersign.
              </p>
              {#if customer.may_manage}
                <form class="stack" onsubmit={savePeople}>
                  {#if customer.assignable?.length}
                    <fieldset class="checks people">
                      <legend class="visually-hidden">Assigned people</legend>
                      {#each customer.assignable as person (person.id)}
                        <label class="check">
                          <input type="checkbox" value={person.id} bind:group={people} />
                          <span>
                            <span class="check-title">{person.display_name}</span>
                            <span class="small muted">
                              {person.roles.filter((r) => r === "technician" || r === "reviewer").map(roleName).join(", ")}
                              · <span class="mono">{person.username}</span>
                            </span>
                          </span>
                        </label>
                      {/each}
                    </fieldset>
                    <div><button class="button button-primary" type="submit" disabled={busy}>Save</button></div>
                  {:else}
                    <p class="muted">
                      Nobody has the Technician or Reviewer role yet. Give someone a role in Admin →
                      Users, then assign them here.
                    </p>
                  {/if}
                </form>
              {:else if customer.assigned?.length}
                <ul class="plain">
                  {#each customer.assigned as person (person.id)}
                    <li>{person.display_name} <span class="muted">· {person.roles.map(roleName).join(", ")}</span></li>
                  {/each}
                </ul>
              {:else}
                <p class="muted">Nobody is assigned yet.</p>
              {/if}
            </section>
          {/if}
        </div>
      {/if}
    </main>
  </AppShell>

  <Dialog bind:open={siteOpen} title={site?.id ? "Change site" : "Add site"}>
    {#if site}
      <form class="stack" onsubmit={saveSite}>
        {#if dialogError}<p class="alert alert-critical" role="alert">{dialogError}</p>{/if}
        <div class="field">
          <label for="site-name">Name</label>
          <input id="site-name" class="input" required maxlength="150" bind:value={site.name} />
          <span class="hint">Such as “Head office” or “Datacentre Aarhus”.</span>
        </div>
        <div class="field">
          <label for="site-address">Address</label>
          <textarea id="site-address" class="input" rows="3" maxlength="500"
            bind:value={site.address}></textarea>
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
        {#if dialogError}<p class="alert alert-critical" role="alert">{dialogError}</p>{/if}
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

  <Dialog bind:open={deleteOpen} title="Delete {customer?.name ?? 'customer'}">
    <form class="stack" onsubmit={deleteCustomer}>
      {#if dialogError}<p class="alert alert-critical" role="alert">{dialogError}</p>{/if}
      <p>
        Its sites, contacts, {customer?.active_projects ?? 0} active and
        {customer?.archived_projects ?? 0} archived projects go too, with its encryption key, so
        nothing that was encrypted with it can be read again. This can't be undone.
      </p>
      <div class="field">
        <label for="delete-name">Type the customer's name to confirm</label>
        <input id="delete-name" class="input" autocomplete="off" required bind:value={deleteName} />
      </div>
      <div class="button-row end">
        <button class="button button-secondary" type="button" onclick={() => (deleteOpen = false)}>Cancel</button>
        <button class="button button-primary danger-fill" type="submit"
          disabled={busy || deleteName.trim() !== customer?.name}>Delete for good</button>
      </div>
    </form>
  </Dialog>
{/if}

<style>
  .who {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    margin-top: var(--space-1);
  }
  .logo {
    width: auto;
    max-width: 160px;
    height: 48px;
    object-fit: contain;
  }
  .logo-placeholder {
    display: grid;
    place-items: center;
    width: 48px;
    height: 48px;
    border-radius: var(--radius-md);
    background: var(--surface-subtle);
    color: var(--text-muted);
  }
  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    border-bottom: 1px solid var(--border);
  }
  .tabs button {
    padding: 10px 14px;
    border: 0;
    border-bottom: 2px solid transparent;
    background: none;
    color: var(--text-muted);
    font: var(--type-label);
    cursor: pointer;
  }
  .tabs button[aria-selected="true"] {
    border-bottom-color: var(--accent);
    color: var(--text);
  }
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
  .form-wide {
    max-width: 640px;
  }
  .people {
    margin: 0;
    padding: 0;
    border: 0;
  }
  .plain {
    margin: 0;
    padding-left: 1.2em;
  }
  .end {
    justify-content: flex-end;
  }
  .danger-zone {
    border-color: var(--critical-text);
  }
  .danger {
    border-color: var(--critical-text);
    color: var(--critical-text);
  }
  .danger-fill {
    background: var(--critical-text);
    color: var(--surface);
  }
</style>
