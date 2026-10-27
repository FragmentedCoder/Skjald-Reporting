<script lang="ts">
  import { onDestroy, tick } from "svelte";
  import { ApiError, sessionGone } from "#lib/api.js";
  import { Engine } from "#lib/cel/engine.js";
  import BlockList from "#lib/components/builder/BlockList.svelte";
  import BlockPanel from "#lib/components/builder/BlockPanel.svelte";
  import Palette, { type PaletteEntry } from "#lib/components/builder/Palette.svelte";
  import ProblemList from "#lib/components/builder/ProblemList.svelte";
  import Where from "#lib/components/builder/Where.svelte";
  import Dialog from "#lib/components/Dialog.svelte";
  import PdfPages from "#lib/components/preview/PdfPages.svelte";
  import { templatesApi, type Asset } from "#lib/templates/api.js";
  import { BLOCK_GROUPS, BLOCK_TYPES, newBlock } from "#lib/templates/blocks.js";
  import { catalogue, type NameEntry } from "#lib/templates/catalogue.js";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import { settingsOf } from "#lib/templates/fields.js";
  import { LivePreview } from "#lib/templates/live.svelte.js";
  import { declarations, ITEM } from "#lib/templates/names.js";
  import { sampleContext } from "#lib/templates/preview.js";
  import { shapeOf } from "#lib/templates/rules.js";
  import { questionsOf, type Block, type BlockKind, type Problem, type TemplateContent } from "#lib/templates/types.js";
  import { toast } from "#lib/toast.svelte.js";

  // The Layout tab: the PDF, built from blocks. The outline shows them in the order
  // they print, with sections and columns holding their own; the pages show what the
  // sample answers print, by the same page rules as the PDF.
  const draft = useDraft();
  const content = $derived(draft.content as TemplateContent);
  let view = $state<"blocks" | "pages">("blocks");

  const palette: PaletteEntry[] = BLOCK_GROUPS.flatMap((group) =>
    (Object.entries(BLOCK_TYPES) as [BlockKind, (typeof BLOCK_TYPES)[BlockKind]][])
      .filter(([, t]) => t.group === group)
      .map(([kind, t]) => ({ kind, label: t.label, hint: t.hint, icon: t.icon, group })),
  );

  const names = $derived(JSON.stringify(declarations(content, draft.libraryNames)));
  const engine = $derived(new Engine(JSON.parse(names), { language: content.settings.language }));
  const itemEngine = $derived(new Engine({ ...JSON.parse(names), ...ITEM }, { language: content.settings.language }));
  const entries = $derived(catalogue(content, draft.libraryNames, draft.libraryLabels));

  // Where a block sits: the list holding it, and the section it's repeated with, if any.
  interface Found {
    block: Block;
    list: Block[];
    index: number;
    repeat: string | null;
  }

  function locate(blocks: Block[], id: string, repeat: string | null = null): Found | null {
    for (const [index, block] of blocks.entries()) {
      if (block.id === id) return { block, list: blocks, index, repeat };
      const inner = block.kind === "section" ? [block.blocks] : block.kind === "columns" ? block.columns : [];
      const nextRepeat = block.kind === "section" && block.repeat_for ? block.repeat_for : repeat;
      for (const list of inner) {
        const found = locate(list, id, nextRepeat);
        if (found) return found;
      }
    }
    return null;
  }

  const selectedId = $derived(draft.selection?.kind === "block" ? draft.selection.id : null);
  const found = $derived(selectedId ? locate(content.layout, selectedId) : null);

  // Inside a repeated section (and in a repeated section's own rule and title), rules
  // also read item, the row it's printed for.
  const repeat = $derived(found ? (found.block.kind === "section" && found.block.repeat_for ? found.block.repeat_for : found.repeat) : null);
  const blockEntries = $derived.by((): NameEntry[] => {
    if (!repeat) return entries;
    const group = questionsOf(content).find((q) => `answers.${q.key}` === repeat);
    const columns = group ? (settingsOf(group.type, group.settings).columns as { key: string; label: string; type: string; settings?: Record<string, unknown> }[]) : [];
    const type = (c: { type: string; settings?: Record<string, unknown> }) =>
      c.type === "number" ? (c.settings?.whole ? "int" : "double") : c.type === "yes_no" ? "bool" : "string";
    return [
      ...columns.map((c) => ({ name: `item.${c.key}`, label: `${c.label}, for this row`, group: "Each row", type: "dyn", shape: shapeOf(type(c)) })),
      ...entries,
    ];
  });

  function select(id: string) {
    draft.selection = { kind: "block", id };
  }

  async function focusPanel() {
    await tick();
    document.querySelector<HTMLElement>(".panel input, .panel textarea, .panel select")?.focus();
  }

  function add(kind: string) {
    if (draft.readonly) return;
    const target = found?.block.kind === "section" ? found.block.blocks : found?.list ?? content.layout;
    const nested = target !== content.layout;
    const block = newBlock(kind as BlockKind, nested);
    const at = found && found.block.kind !== "section" ? found.index + 1 : target.length;
    target.splice(at, 0, block);
    select(block.id);
    void focusPanel();
  }

  function move(by: number) {
    if (!found) return;
    const { list, index, block } = found;
    const to = index + by;
    if (to < 0 || to >= list.length) return;
    list.splice(index, 1);
    list.splice(to, 0, block);
  }

  let confirming = $state(false);
  function remove() {
    if (!found) return;
    const holds = found.block.kind === "section" ? found.block.blocks.length : found.block.kind === "columns" ? found.block.columns.flat().length : 0;
    if (holds) confirming = true;
    else removeNow();
  }
  function removeNow() {
    if (!found) return;
    found.list.splice(found.index, 1);
    draft.selection = null;
    confirming = false;
  }

  async function upload(file: File): Promise<Asset | null> {
    try {
      const asset = await templatesApi.upload(draft.id, file);
      if (draft.template) draft.template = await templatesApi.get(draft.id);
      return asset;
    } catch (e) {
      if (!sessionGone(e)) toast(e instanceof ApiError ? e.message : "The image couldn't be added.", "critical");
      return null;
    }
  }

  // The preview, worked out again a moment after each change.
  const live = new LivePreview();
  onDestroy(() => live.close());
  $effect(() => {
    const snapshot = $state.snapshot(content) as TemplateContent;
    const assets = Object.fromEntries((draft.template?.assets ?? []).map((a) => [a.sha256, { url: a.url, width: a.width, height: a.height }]));
    live.update({ content: snapshot, answers: snapshot.sample.answers, context: sampleContext(), assets, library: draft.libraryPreview });
  });
  const hidden = $derived(new Map((live.model?.hidden ?? []).map((h) => [h.id, h.reason])));

  function show(problem: Problem) {
    if (locate(content.layout, problem.element)) {
      select(problem.element);
      void focusPanel();
    }
  }
</script>

{#if draft.readonly}
  <p class="alert alert-info small">This is version {draft.shownVersion}, which reports use. Choose Edit to change it in a new draft.</p>
{/if}

<div class="workspace" class:readonly={draft.readonly}>
  {#if !draft.readonly}
    <Palette entries={palette} type="blocks" title="Blocks" onadd={add} />
  {/if}

  <section class="canvas" aria-labelledby="layout-title">
    <div class="intro">
      <div class="title-line">
        <h2 id="layout-title" class="section-title">The PDF <Where pdf /></h2>
        <div class="views" role="group" aria-label="Show">
          <button type="button" aria-pressed={view === "blocks"} onclick={() => (view = "blocks")}>Blocks</button>
          <button type="button" aria-pressed={view === "pages"} onclick={() => (view = "pages")}>Pages</button>
        </div>
      </div>
      <p class="small muted">
        {view === "blocks"
          ? "Everything here is printed, in this order, for the customer. Drag blocks into place, or click one in the palette."
          : "What the sample answers print, by the same page rules as the PDF. Click a block to change it."}
      </p>
    </div>

    {#if view === "blocks"}
      <BlockList bind:blocks={content.layout} label="Blocks in the PDF" selected={selectedId} {hidden}
        problems={(id) => draft.problemsFor(id).length} readonly={draft.readonly} onselect={select} />
      {#if !content.layout.length}<p class="empty small muted">Drag a block here, or click one in the palette.</p>{/if}
    {:else if live.paged}
      {#if live.problem}<p class="alert alert-warning small">{live.problem}</p>{/if}
      {#if live.model?.errors.length}
        <p class="alert alert-warning small">{live.model.errors.length} expression{live.model.errors.length === 1 ? "" : "s"} failed with the sample answers, shown as ⚠ on the pages.</p>
      {/if}
      <PdfPages paged={live.paged} classification={String(sampleContext().project.classification)} selected={selectedId} onselect={select} />
    {:else}
      <p class="muted">Working out the pages…</p>
    {/if}
  </section>

  <aside class="panel" aria-label="Settings of what's selected">
    <fieldset class="unstyled" disabled={draft.readonly}>
      {#if found}
        <BlockPanel block={found.block} {content} engine={repeat ? itemEngine : engine} entries={blockEntries}
          problems={draft.problemsFor(found.block.id)} assets={draft.template?.assets ?? []}
          first={found.index === 0} last={found.index === found.list.length - 1}
          onupload={upload} onremove={remove} onmove={move} />
      {:else}
        <p class="small muted">Select a block to change it.</p>
      {/if}
    </fieldset>
  </aside>
</div>

{#if !draft.readonly}
  <ProblemList problems={draft.problems} {content} onselect={show} />
{/if}

<Dialog bind:open={confirming} title="Remove it?">
  <p>The blocks inside it go with it.</p>
  {#snippet actions()}
    <button class="button button-secondary" type="button" onclick={() => (confirming = false)}>Keep it</button>
    <button class="button button-primary" type="button" onclick={removeNow}>Remove</button>
  {/snippet}
</Dialog>

<style>
  .workspace {
    display: grid;
    grid-template-columns: 210px minmax(0, 1fr) minmax(290px, 380px);
    gap: var(--space-4);
    align-items: start;
    margin-top: var(--space-4);
  }
  .workspace.readonly {
    grid-template-columns: minmax(0, 1fr) minmax(290px, 380px);
  }
  .title-line {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .section-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .intro p {
    margin: var(--space-1) 0 var(--space-3);
  }
  .views {
    display: inline-flex;
    padding: 2px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }
  .views button {
    padding: 4px 12px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  .views button[aria-pressed="true"] {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .empty {
    padding: var(--space-4);
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius-md);
    text-align: center;
  }
  .panel {
    position: sticky;
    top: var(--space-4);
    max-height: calc(100vh - 2 * var(--space-4));
    overflow-y: auto;
    padding: var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .unstyled {
    min-width: 0;
    margin: 0;
    padding: 0;
    border: 0;
  }
  @media (max-width: 1100px) {
    .workspace,
    .workspace.readonly {
      grid-template-columns: minmax(0, 1fr);
    }
    .panel {
      position: static;
      max-height: none;
    }
  }
</style>
