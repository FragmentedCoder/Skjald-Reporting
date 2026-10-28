<script lang="ts">
  import { onMount } from "svelte";
  import { customFieldsApi, type AppliesTo, type CustomField } from "#lib/customFields.js";
  import { date } from "#lib/format.js";

  // Custom fields' values, as terms and descriptions inside a <dl>: those filled in only.
  let { appliesTo, values }: { appliesTo: AppliesTo; values: Record<string, unknown> | null } = $props();
  let fields = $state<CustomField[]>([]);
  onMount(async () => {
    fields = (await customFieldsApi.list().catch(() => [])).filter((f) => f.applies_to === appliesTo);
  });

  function shown(field: CustomField, value: unknown): string {
    if (field.type === "yes_no") return value ? "Yes" : "No";
    if (field.type === "date" && typeof value === "string") return date(value);
    return String(value);
  }
</script>

{#each fields.filter((f) => values?.[f.key] !== undefined && values?.[f.key] !== "") as field (field.id)}
  <dt>{field.label}</dt>
  <dd>{shown(field, values?.[field.key])}</dd>
{/each}
