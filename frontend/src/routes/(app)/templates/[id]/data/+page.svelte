<script lang="ts">
  import { onDestroy } from "svelte";
  import Where from "#lib/components/builder/Where.svelte";
  import FunctionsReference from "#lib/components/database/FunctionsReference.svelte";
  import NamesBrowser from "#lib/components/database/NamesBrowser.svelte";
  import TryExpression from "#lib/components/database/TryExpression.svelte";
  import { catalogue } from "#lib/templates/catalogue.js";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import { LivePreview } from "#lib/templates/live.svelte.js";
  import { nameGroups } from "#lib/templates/nameGroups.js";
  import { declarations } from "#lib/templates/names.js";
  import type { TemplateContent } from "#lib/templates/types.js";

  // The Data tab: every name the template can read, its answers first, to search and
  // look up (what each is, its kind, an example from the sample answers); a box to try
  // an expression on the sample answers; and a reference for every function. The
  // Database page and the editor's Names drawer show the same lists.
  const draft = useDraft();
  const content = $derived(draft.content as TemplateContent);
  const entries = $derived(catalogue(content, draft.libraryNames, draft.libraryLabels));
  const declared = $derived(declarations(content, draft.libraryNames));

  // The sample answers as expressions read them, calculated values worked out.
  const live = new LivePreview();
  onDestroy(() => live.close());
  $effect(() => {
    const snapshot = $state.snapshot(content) as TemplateContent;
    live.update({ content: snapshot, answers: snapshot.sample.answers, context: draft.sampleContext, assets: {}, library: draft.libraryPreview });
  });

  const values = $derived({ ...draft.sampleContext, ...draft.libraryPreview.values, answers: live.model?.values ?? {} });
  const groups = $derived(nameGroups(entries, values, draft.library));
</script>

<div class="data">
  <section class="section" aria-labelledby="try-title">
    <h2 id="try-title" class="section-title">Try an expression <Where builder /></h2>
    <TryExpression declarations={declared} {values} language={content.settings.language} tables={draft.libraryPreview.tables}
      about={"Worked out on the sample answers, the way rules and text in {{ }} are."} />
  </section>

  <NamesBrowser {groups} />

  <FunctionsReference />
</div>

<style>
  .data {
    display: grid;
    gap: var(--space-4);
    margin-top: var(--space-4);
  }
  .section-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
</style>
