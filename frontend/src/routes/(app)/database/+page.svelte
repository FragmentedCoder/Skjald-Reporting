<script lang="ts">
  import { onMount } from "svelte";
  import Where from "#lib/components/builder/Where.svelte";
  import FunctionsReference from "#lib/components/database/FunctionsReference.svelte";
  import NamesBrowser from "#lib/components/database/NamesBrowser.svelte";
  import TryExpression from "#lib/components/database/TryExpression.svelte";
  import { customFieldsApi, customLabels, customNames, sampleCustom, type CustomField } from "#lib/customFields.js";
  import { libraryApi, libraryLabels, libraryNames, libraryValues, type LibraryEntry } from "#lib/library.js";
  import { catalogue } from "#lib/templates/catalogue.js";
  import { nameGroups } from "#lib/templates/nameGroups.js";
  import { declarations } from "#lib/templates/names.js";
  import { sampleContext } from "#lib/templates/preview.js";

  // All names: what any template can read besides its own answers (the report's
  // details, custom fields, the library), each with what it is, its kind and an
  // example; a box to try an expression on those examples; and every function.
  let library = $state<LibraryEntry[]>([]);
  let fields = $state<CustomField[]>([]);
  onMount(async () => {
    [library, fields] = await Promise.all([libraryApi.list().catch(() => []), customFieldsApi.list().catch(() => [])]);
  });

  const names = $derived({ ...libraryNames(library), ...customNames(fields) });
  const entries = $derived(catalogue(null, names, { ...libraryLabels(library), ...customLabels(fields) }));
  const shared = $derived(libraryValues(library));
  const values = $derived({ ...sampleContext({ customer: sampleCustom(fields, "customer"), project: sampleCustom(fields, "project") }), ...shared.values });
  const groups = $derived(nameGroups(entries, values, library));
</script>

<div class="names">
  <section class="section" aria-labelledby="try-title">
    <h2 id="try-title" class="section-title">Try an expression <Where builder /></h2>
    <TryExpression declarations={declarations(null, names)} {values} tables={shared.tables}
      about={"Worked out on the examples below, the way rules and text in {{ }} are. A template's own answers (answers.…) are on its Data tab and in its Names drawer."} />
  </section>

  <NamesBrowser {groups} />

  <FunctionsReference />
</div>

<style>
  .names {
    display: grid;
    gap: var(--space-4);
  }
  .section-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
</style>
