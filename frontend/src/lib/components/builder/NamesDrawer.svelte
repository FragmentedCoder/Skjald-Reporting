<script lang="ts">
  import X from "@lucide/svelte/icons/x";
  import { onDestroy } from "svelte";
  import NamesBrowser from "#lib/components/database/NamesBrowser.svelte";
  import TryExpression from "#lib/components/database/TryExpression.svelte";
  import { catalogue } from "#lib/templates/catalogue.js";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import { LivePreview } from "#lib/templates/live.svelte.js";
  import { nameGroups, type NameRow } from "#lib/templates/nameGroups.js";
  import { declarations } from "#lib/templates/names.js";
  import { nameTarget } from "#lib/templates/nameTarget.svelte.js";
  import type { TemplateContent } from "#lib/templates/types.js";
  import { toast } from "#lib/toast.svelte.js";

  // The Names drawer, beside whichever tab of the builder is open: every name this
  // template can read, to search and look up, and a box to try an expression, without
  // leaving the field being written. A name clicked goes where the caret was in the
  // last text field typed in; with none, it's copied.
  let { onclose }: { onclose: () => void } = $props();

  const draft = useDraft();
  const content = $derived(draft.content as TemplateContent);
  const live = new LivePreview();
  onDestroy(() => live.close());
  $effect(() => {
    const snapshot = $state.snapshot(content) as TemplateContent;
    live.update({ content: snapshot, answers: snapshot.sample.answers, context: draft.sampleContext, assets: {}, library: draft.libraryPreview });
  });
  const values = $derived({ ...draft.sampleContext, ...draft.libraryPreview.values, answers: live.model?.values ?? {} });
  const groups = $derived(nameGroups(catalogue(content, draft.libraryNames, draft.libraryLabels), values, draft.library));

  async function pick(row: NameRow) {
    const target = nameTarget.current;
    if (target) {
      target.insert(row.name);
      toast(`Inserted {{${row.name}}} in ${target.label}.`, "ok", { key: "names-drawer" });
      return;
    }
    try {
      await navigator.clipboard.writeText(`{{${row.name}}}`);
      toast(`Copied {{${row.name}}}: click in a text field first to insert names straight into it.`, "info", { key: "names-drawer" });
    } catch {
      toast(`Click in a text field first, then pick the name to insert it.`, "warning", { key: "names-drawer" });
    }
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === "Escape" && !document.querySelector("dialog[open]")) onclose();
  }
</script>

<svelte:window onkeydown={keydown} />

<aside class="drawer" id="names-drawer" aria-label="Names">
  <div class="head">
    <h2 class="title">Names</h2>
    <button class="icon-button" type="button" aria-label="Close the names" title="Close (Esc)" onclick={onclose}><X size={18} aria-hidden="true" /></button>
  </div>
  <p class="small muted">
    {nameTarget.current ? `Click a name to insert it in ${nameTarget.current.label}, where the caret was.` : "Click in a text field, then click a name to insert it there."}
  </p>
  <details class="try">
    <summary>Try an expression</summary>
    <TryExpression id="drawer-expression" declarations={declarations(content, draft.libraryNames)} {values} language={content.settings.language}
      tables={draft.libraryPreview.tables} about={"An expression, a name in {{ }}, or text with names in {{ }}, worked out on the sample answers."} />
  </details>
  <NamesBrowser {groups} compact onpick={pick} id="drawer-names" />
</aside>

<style>
  .drawer {
    position: fixed;
    z-index: 30;
    top: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    width: min(400px, 100vw);
    padding: var(--space-4);
    overflow-y: auto;
    border-left: 1px solid var(--border);
    background: var(--bg);
    box-shadow: -8px 0 24px rgb(15 27 45 / 0.12);
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .title {
    margin: 0;
    font: var(--type-subheading);
  }
  .drawer > p {
    margin: 0;
  }
  .try summary {
    font-weight: 600;
    cursor: pointer;
  }
  .try[open] summary {
    margin-bottom: var(--space-2);
  }
</style>
