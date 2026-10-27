<script lang="ts">
  import CustomFieldInputs from "#lib/components/CustomFieldInputs.svelte";
  import { LANGUAGES } from "#lib/customers.js";

  // A customer's own details, for adding one and for changing them.
  let {
    values = $bindable(),
  }: {
    values: { name: string; cvr: string; address: string; language: string; retention_months: number; custom: Record<string, unknown> };
  } = $props();

  const uid = $props.id();
</script>

<div class="field">
  <label for="{uid}-name">Name</label>
  <input id="{uid}-name" class="input" required maxlength="200" autocomplete="organization"
    bind:value={values.name} />
  <span class="hint">The legal name, as it goes on reports.</span>
</div>
<div class="field">
  <label for="{uid}-cvr">CVR number (optional)</label>
  <input id="{uid}-cvr" class="input cvr" inputmode="numeric" maxlength="11"
    aria-describedby="{uid}-cvr-hint" bind:value={values.cvr} />
  <span class="hint" id="{uid}-cvr-hint">8 digits. Leave it empty for a customer outside Denmark.</span>
</div>
<div class="field">
  <label for="{uid}-address">Address</label>
  <textarea id="{uid}-address" class="input" rows="3" maxlength="1000"
    bind:value={values.address}></textarea>
  <span class="hint">Kept encrypted with the customer's own key.</span>
</div>
<div class="field">
  <label for="{uid}-language">Report language</label>
  <select id="{uid}-language" class="input select" bind:value={values.language}>
    {#each LANGUAGES as language (language.value)}
      <option value={language.value}>{language.name}</option>
    {/each}
  </select>
</div>
<div class="field">
  <label for="{uid}-retention">Keep raw data for</label>
  <input id="{uid}-retention" class="input number" type="number" min="1" max="120" required
    aria-describedby="{uid}-retention-hint" bind:value={values.retention_months} />
  <span class="hint" id="{uid}-retention-hint">
    Months after a project is archived: uploads, imports and data bundles. Signed reports are
    kept at least 5 years either way. From 1 to 120.
  </span>
</div>

<CustomFieldInputs appliesTo="customer" bind:values={values.custom} />

<style>
  .cvr,
  .number,
  .select {
    max-width: 12rem;
  }
</style>
