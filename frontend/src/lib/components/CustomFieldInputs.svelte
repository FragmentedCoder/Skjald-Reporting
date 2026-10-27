<script lang="ts">
  import { onMount } from "svelte";
  import { customFieldsApi, type AppliesTo, type CustomField } from "#lib/customFields.js";

  // The company's custom fields for a customer or a project, as inputs. An emptied field
  // is sent as "", which clears its value. Kept encrypted with the customer's own key.
  let {
    appliesTo,
    values = $bindable(),
  }: {
    appliesTo: AppliesTo;
    values: Record<string, unknown>;
  } = $props();

  let fields = $state<CustomField[]>([]);
  const uid = $props.id();

  onMount(async () => {
    fields = (await customFieldsApi.list().catch(() => [])).filter((f) => f.applies_to === appliesTo);
  });

  const text = (key: string) => (values[key] === undefined || values[key] === null ? "" : String(values[key]));

  function setNumber(key: string, raw: string) {
    values[key] = raw === "" ? "" : Number(raw);
  }

  function setYesNo(key: string, raw: string) {
    values[key] = raw === "" ? "" : raw === "yes";
  }
</script>

{#if fields.length}
  <fieldset class="custom stack">
    <legend>{appliesTo === "customer" ? "More about the customer" : "More about the project"}</legend>
    {#each fields as field (field.id)}
      {@const id = `${uid}-${field.key}`}
      <div class="field">
        <label for={id}>{field.label} <span class="muted">(optional)</span></label>
        {#if field.type === "long_text"}
          <textarea {id} class="input" rows="3" maxlength="5000" value={text(field.key)} oninput={(e) => (values[field.key] = e.currentTarget.value)}></textarea>
        {:else if field.type === "number"}
          <input {id} class="input short" type="number" step="any" value={text(field.key)} oninput={(e) => setNumber(field.key, e.currentTarget.value)} />
        {:else if field.type === "date"}
          <input {id} class="input short" type="date" value={text(field.key)} oninput={(e) => (values[field.key] = e.currentTarget.value)} />
        {:else if field.type === "yes_no"}
          <select {id} class="input short" value={values[field.key] === true ? "yes" : values[field.key] === false ? "no" : ""} onchange={(e) => setYesNo(field.key, e.currentTarget.value)}>
            <option value="">Not set</option><option value="yes">Yes</option><option value="no">No</option>
          </select>
        {:else if field.type === "dropdown"}
          <select {id} class="input" value={text(field.key)} onchange={(e) => (values[field.key] = e.currentTarget.value)}>
            <option value="">Not set</option>
            {#each field.options as option (option)}<option value={option}>{option}</option>{/each}
          </select>
        {:else}
          <input {id} class="input" type={field.type === "email" ? "email" : field.type === "phone" ? "tel" : "text"} maxlength="500"
            value={text(field.key)} oninput={(e) => (values[field.key] = e.currentTarget.value)} />
        {/if}
        {#if field.help}<span class="hint">{field.help}</span>{/if}
      </div>
    {/each}
  </fieldset>
{/if}

<style>
  .custom {
    margin: 0;
    padding: 0;
    border: 0;
  }
  legend {
    margin-bottom: var(--space-3);
    font-weight: 600;
  }
  .short {
    max-width: 12rem;
  }
</style>
