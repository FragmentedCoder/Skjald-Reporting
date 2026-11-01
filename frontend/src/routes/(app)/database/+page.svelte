<script lang="ts">
  import { onMount } from "svelte";
  import Where from "#lib/components/builder/Where.svelte";
  import FunctionsReference from "#lib/components/database/FunctionsReference.svelte";
  import NamesBrowser from "#lib/components/database/NamesBrowser.svelte";
  import TryExpression from "#lib/components/database/TryExpression.svelte";
  import { customFieldsApi, customLabels, customNames, sampleCustom, type CustomField } from "#lib/customFields.js";
  import { libraryApi, libraryLabels, libraryNames, libraryValues, type LibraryEntry } from "#lib/library.js";
  import { catalogue } from "#lib/templates/catalogue.js";
  import { currentValues, withCurrent, type Current } from "#lib/templates/current.js";
  import { nameGroups } from "#lib/templates/nameGroups.js";
  import { declarations } from "#lib/templates/names.js";
  import { sampleContext } from "#lib/templates/preview.js";
  import { openCustomer, workspace } from "#lib/workspace.svelte.js";

  // All names: what any template can read besides its own answers (the report's
  // details, custom fields, the library), each with what it is, its kind and an
  // example: what's there now where there's something (current.ts), else a made-up
  // one. Then a box to try an expression on those values, and every function.
  let library = $state<LibraryEntry[]>([]);
  let fields = $state<CustomField[]>([]);
  let current = $state<Current>({ values: {}, sources: [] });
  onMount(async () => {
    [library, fields] = await Promise.all([libraryApi.list().catch(() => []), customFieldsApi.list().catch(() => [])]);
  });
  // Fetched again when another customer or project is opened in the side menu; only
  // the newest answer is used.
  const opened = $derived(`${openCustomer()?.id}|${workspace.project?.id ?? workspace.projects?.[0]?.id}`);
  let asked = 0;
  $effect(() => {
    void opened;
    const mine = ++asked;
    void currentValues().then((found) => {
      if (mine === asked) current = found;
    });
  });

  const names = $derived({ ...libraryNames(library), ...customNames(fields) });
  const entries = $derived(catalogue(null, names, { ...libraryLabels(library), ...customLabels(fields) }));
  const shared = $derived(libraryValues(library));
  const filled = $derived(withCurrent(sampleContext({ customer: sampleCustom(fields, "customer"), project: sampleCustom(fields, "project") }), current.values));
  const values = $derived({ ...filled.values, ...shared.values });
  const groups = $derived(nameGroups(entries, values, library, filled.live));

  /** "a, b and c" */
  const listed = (items: string[]) => (items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items.at(-1)}` : (items[0] ?? ""));
</script>

<div class="names">
  <section class="section" aria-labelledby="try-title">
    <h2 id="try-title" class="section-title">Try an expression <Where builder /></h2>
    <TryExpression declarations={declarations(null, names)} {values} tables={shared.tables}
      about={"Write an expression as rules have it, a name in {{ }}, or text with names in {{ }} as a text block has, and see what it gives with the examples below. A template's own answers (answers.…) are on its Data tab and in its Names drawer."} />
  </section>

  <div class="list">
    <p class="small muted legend">
      {#if current.sources.length}Examples in plain text are what's there now, from {listed(current.sources)}.{/if}
      <span class="made-up">Those in grey italics are made up</span>: a report's own details exist only once a report is
      written, and an empty detail keeps its example.
      {#if !current.sources.some((s) => s.includes("side menu"))}Open a customer in the side menu to see its details here.{/if}
    </p>
    <NamesBrowser {groups} />
  </div>

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
  .list {
    display: grid;
    gap: var(--space-2);
  }
  .legend {
    margin: 0;
  }
  .made-up {
    font-style: italic;
  }
</style>
