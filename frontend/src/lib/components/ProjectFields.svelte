<script lang="ts" module>
  export interface ProjectForm {
    name: string;
    start_date: string;
    end_date: string;
    responsible_id: string;
    reviewer_id: string;
    contact_id: string;
    site_ids: number[];
    classification: string;
    /** Custom fields' values by key. */
    custom: Record<string, unknown>;
  }

  /** The request body for a form: empty choices become null. */
  export function projectBody(form: ProjectForm) {
    return {
      name: form.name,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      responsible_id: form.responsible_id ? Number(form.responsible_id) : null,
      reviewer_id: form.reviewer_id ? Number(form.reviewer_id) : null,
      contact_id: form.contact_id ? Number(form.contact_id) : null,
      site_ids: form.site_ids,
      classification: form.classification,
      custom: form.custom,
    };
  }
</script>

<script lang="ts">
  import CustomFieldInputs from "#lib/components/CustomFieldInputs.svelte";
  import { CLASSIFICATIONS, reviewers, technicians, type CustomerDetail } from "#lib/customers.js";

  // A project's fields; the choices (technicians, reviewers, contacts, sites) are the
  // customer's. Nobody reviews their own report, so whoever is responsible isn't
  // offered as the reviewer, and the other way round.
  let { values = $bindable(), customer }: { values: ProjectForm; customer: CustomerDetail } = $props();

  const uid = $props.id();
  const people = $derived(technicians(customer.assigned)
    .filter((p) => String(p.id) !== values.reviewer_id));
  const checkers = $derived(reviewers(customer.assigned)
    .filter((p) => String(p.id) !== values.responsible_id));
</script>

<div class="field">
  <label for="{uid}-name">Name</label>
  <input id="{uid}-name" class="input" required maxlength="200" bind:value={values.name} />
  <span class="hint">Such as “Ransomware incident, October” or “Yearly penetration test”.</span>
</div>
<div class="dates">
  <div class="field">
    <label for="{uid}-start">Start date</label>
    <input id="{uid}-start" class="input" type="date" bind:value={values.start_date} />
  </div>
  <div class="field">
    <label for="{uid}-end">End date</label>
    <input id="{uid}-end" class="input" type="date" min={values.start_date || undefined}
      bind:value={values.end_date} />
  </div>
</div>
<div class="field">
  <label for="{uid}-responsible">Responsible technician</label>
  <select id="{uid}-responsible" class="input" bind:value={values.responsible_id}>
    <option value="">Nobody yet</option>
    {#each people as person (person.id)}
      <option value={String(person.id)}>{person.display_name}</option>
    {/each}
  </select>
  <span class="hint">One of the technicians assigned to {customer.name}. Writes the reports.</span>
</div>
<div class="field">
  <label for="{uid}-reviewer">Reviewer</label>
  <select id="{uid}-reviewer" class="input" bind:value={values.reviewer_id}>
    <option value="">Nobody yet</option>
    {#each checkers as person (person.id)}
      <option value={String(person.id)}>{person.display_name}</option>
    {/each}
  </select>
  <span class="hint">
    One of the reviewers assigned to {customer.name}. Reviews and countersigns the reports, and
    can't change the project.
  </span>
</div>
<div class="field">
  <label for="{uid}-contact">Customer contact</label>
  <select id="{uid}-contact" class="input" bind:value={values.contact_id}>
    <option value="">None</option>
    {#each customer.contacts ?? [] as contact (contact.id)}
      <option value={String(contact.id)}>{contact.name}{contact.role ? `, ${contact.role}` : ""}</option>
    {/each}
  </select>
</div>
{#if customer.sites?.length}
  <fieldset class="checks sites">
    <legend class="check-title">Sites</legend>
    {#each customer.sites as site (site.id)}
      <label class="check">
        <input type="checkbox" value={site.id} bind:group={values.site_ids} />
        <span>{site.name}</span>
      </label>
    {/each}
  </fieldset>
{/if}
<fieldset class="checks classification">
  <legend class="check-title">Classification</legend>
  <p class="small muted">Printed on every page of the project's reports (Traffic Light Protocol).</p>
  {#each CLASSIFICATIONS as option (option.value)}
    <label class="check">
      <input type="radio" name="{uid}-classification" value={option.value}
        bind:group={values.classification} />
      <span>
        <span class="check-title mono">{option.value}</span>
        <span class="small muted">{option.hint}</span>
      </span>
    </label>
  {/each}
</fieldset>

<CustomFieldInputs appliesTo="project" bind:values={values.custom} />

<style>
  .dates {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 220px));
    gap: var(--space-4);
  }
  .sites,
  .classification {
    margin: 0;
    padding: 0;
    border: 0;
  }
  .sites legend,
  .classification legend {
    margin-bottom: var(--space-2);
  }
  select.input {
    max-width: 420px;
  }
</style>
