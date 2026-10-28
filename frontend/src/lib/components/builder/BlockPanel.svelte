<script lang="ts">
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Plus from "@lucide/svelte/icons/plus";
  import Upload from "@lucide/svelte/icons/upload";
  import X from "@lucide/svelte/icons/x";
  import type { Engine } from "#lib/cel/engine.js";
  import { inkFor } from "#lib/components/preview/PdfPages.svelte";
  import type { Asset } from "#lib/templates/api.js";
  import { BLOCK_TYPES, changeSigner, emptyDoc, nextSigner } from "#lib/templates/blocks.js";
  import type { NameEntry } from "#lib/templates/catalogue.js";
  import { settingsOf } from "#lib/templates/fields.js";
  import { questionsOf, type Block, type Problem, type Signer, type TemplateContent } from "#lib/templates/types.js";
  import NameInput from "./NameInput.svelte";
  import RichTextEditor from "./RichTextEditor.svelte";
  import RuleField from "./RuleField.svelte";
  import Where from "./Where.svelte";

  // Everything about the selected block. All of it is printed in the PDF.
  let { block, content, engine, entries, problems, assets, first, last, onupload, onremove, onmove }: {
    block: Block;
    content: TemplateContent;
    engine: Engine;
    entries: NameEntry[];
    problems: Problem[];
    assets: Asset[];
    first: boolean;
    last: boolean;
    onupload: (file: File) => Promise<Asset | null>;
    onremove: () => void;
    onmove: (by: number) => void;
  } = $props();

  const type = $derived(BLOCK_TYPES[block.kind]);
  const id = $derived(`b-${block.id}`);
  const questions = $derived(questionsOf(content));
  const lists = $derived(questions.filter((q) => q.type === "repeating" || q.type === "table"));
  const photos = $derived(questions.filter((q) => q.type === "photo"));
  const problem = (field: string) => problems.find((p) => p.field === field)?.message ?? null;
  const fieldProblems = (prefix: string) => problems.filter((p) => p.field.startsWith(prefix)).map((p) => p.message);
  const columnsOf = (questionId: string | null) => {
    const q = questions.find((x) => x.id === questionId);
    return q ? (settingsOf(q.type, q.settings).columns as { key: string; label: string }[]) : [];
  };
  const TONES = [
    { value: "info", label: "Info" }, { value: "note", label: "Note" }, { value: "warning", label: "Warning" },
    { value: "critical", label: "Critical" }, { value: "success", label: "Success" },
  ];

  let uploading = $state(false);
  let uploadError = $state<string | null>(null);

  async function upload(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || block.kind !== "image") return;
    uploading = true;
    uploadError = null;
    const asset = await onupload(file);
    uploading = false;
    input.value = "";
    if (asset) block.asset = asset.sha256;
    else uploadError = "The image couldn't be added.";
  }

  const contrastNote = $derived.by(() => {
    if (block.kind !== "callout" || block.tone !== "custom" || !block.colour) return null;
    const { ink, ratio } = inkFor(block.colour);
    return { ink: ink === "#FFFFFF" ? "white" : "Midnat", ratio, low: ratio < 4.5 };
  });
</script>

{#snippet text(field: string, label: string, value: string, set: (v: string) => void, hint = "")}
  <div class="field">
    <label for="{id}-{field}">{label}</label>
    <NameInput id="{id}-{field}" bind:value={() => value, set} {entries} invalid={Boolean(problem(field))} />
    <span class="hint" class:error={problem(field)}>{problem(field) ?? hint}</span>
  </div>
{/snippet}

<div class="panel-head">
  <span class="type"><type.icon size={16} aria-hidden="true" /> {type.label}</span>
  <span class="head-actions">
    <button class="mini" type="button" aria-label="Move up" title="Move up" disabled={first} onclick={() => onmove(-1)}><ArrowUp size={16} aria-hidden="true" /></button>
    <button class="mini" type="button" aria-label="Move down" title="Move down" disabled={last} onclick={() => onmove(1)}><ArrowDown size={16} aria-hidden="true" /></button>
    <button class="mini" type="button" aria-label="Remove the block" title="Remove" onclick={onremove}><X size={16} aria-hidden="true" /></button>
  </span>
</div>

<section class="group" aria-labelledby="{id}-pdf">
  <div class="group-head"><h3 id="{id}-pdf">In the PDF</h3><Where pdf /></div>

  {#if block.kind === "section"}
    {@render text("title", "Title", block.title, (v) => block.kind === "section" && (block.title = v), "Type {{ to insert a name, such as the report's number.")}
    {#if block.intro}
      <RichTextEditor bind:value={block.intro} {entries} label="Introduction, under the heading" id="{id}-intro" />
      <button class="link-button small start" type="button" onclick={() => block.kind === "section" && (block.intro = null)}>Remove the introduction</button>
    {:else}
      <button class="button button-secondary small-button" type="button" onclick={() => block.kind === "section" && (block.intro = emptyDoc())}>Add an introduction</button>
    {/if}
    <label class="check"><input type="checkbox" bind:checked={block.new_page} /> Starts on a new page</label>
    <label class="check"><input type="checkbox" bind:checked={block.numbered} /> Numbered</label>
    <label class="check"><input type="checkbox" bind:checked={block.landscape} /> Landscape pages</label>
    <div class="field">
      <label for="{id}-repeat">Print it once for each</label>
      <select id="{id}-repeat" class="input" value={block.repeat_for ?? ""}
        onchange={(e) => block.kind === "section" && (block.repeat_for = e.currentTarget.value || null)}>
        <option value="">Print it once</option>
        {#each lists.filter((q) => q.key) as q (q.id)}<option value="answers.{q.key}">Row of “{q.label}”</option>{/each}
        {#if block.repeat_for && !lists.some((q) => `answers.${q.key}` === block.repeat_for)}<option value={block.repeat_for}>{block.repeat_for}</option>{/if}
      </select>
      <span class="hint" class:error={problem("repeat_for")}>{problem("repeat_for") ?? "Inside it, rules and text read the row as item, such as item.ip."}</span>
    </div>
  {:else if block.kind === "cover"}
    {@render text("title", "Title", block.title, (v) => block.kind === "cover" && (block.title = v))}
    {@render text("subtitle", "Subtitle", block.subtitle, (v) => block.kind === "cover" && (block.subtitle = v))}
    <fieldset class="plain">
      <legend>Facts</legend>
      {#each block.facts as fact, i (i)}
        <div class="pair">
          <NameInput label="Fact {i + 1}: label" bind:value={fact.label} {entries} />
          <NameInput label="Fact {i + 1}: value" bind:value={fact.value} {entries} />
          <button class="mini" type="button" aria-label="Remove fact {i + 1}" onclick={() => block.kind === "cover" && block.facts.splice(i, 1)}><X size={14} aria-hidden="true" /></button>
        </div>
      {/each}
      {#each fieldProblems("facts") as message, i (i)}<p class="small error">{message}</p>{/each}
      <button class="link-button small start" type="button" onclick={() => block.kind === "cover" && block.facts.push({ label: "", value: "" })}><Plus size={14} aria-hidden="true" /> Add a fact</button>
    </fieldset>
    <label class="check"><input type="checkbox" bind:checked={block.show_logo} /> Show the logo</label>
  {:else if block.kind === "toc"}
    {@render text("title", "Title", block.title, (v) => block.kind === "toc" && (block.title = v))}
    <div class="field">
      <label for="{id}-depth">Lists</label>
      <select id="{id}-depth" class="input" value={String(block.depth)} onchange={(e) => block.kind === "toc" && (block.depth = Number(e.currentTarget.value) as 1 | 2)}>
        <option value="1">Sections</option><option value="2">Sections and the sections inside them</option>
      </select>
    </div>
  {:else if block.kind === "heading"}
    {@render text("text", "Heading", block.text, (v) => block.kind === "heading" && (block.text = v))}
  {:else if block.kind === "text"}
    <RichTextEditor bind:value={() => block.kind === "text" ? block.content : null, (v) => block.kind === "text" && v && (block.content = v)} {entries} label="Text" id="{id}-content" />
    {#if problem("content")}<p class="small error">{problem("content")}</p>{/if}
  {:else if block.kind === "answer"}
    <div class="field">
      <label for="{id}-question">Answer to print</label>
      <select id="{id}-question" class="input" value={block.question ?? ""} onchange={(e) => block.kind === "answer" && (block.question = e.currentTarget.value || null)}>
        <option value="" disabled>Choose a question…</option>
        {#each questions.filter((q) => q.type !== "heading") as q (q.id)}<option value={q.id}>{q.label}</option>{/each}
      </select>
      {#if problem("question")}<span class="hint error">{problem("question")}</span>{/if}
    </div>
    <label class="check"><input type="checkbox" bind:checked={block.show_label} /> Print the question above it</label>
  {:else if block.kind === "table"}
    <div class="field">
      <label for="{id}-question">Rows from</label>
      <select id="{id}-question" class="input" value={block.question ?? ""} onchange={(e) => { if (block.kind === "table") { block.question = e.currentTarget.value || null; block.columns = null; } }}>
        <option value="" disabled>Choose a repeating group or table…</option>
        {#each lists as q (q.id)}<option value={q.id}>{q.label}</option>{/each}
      </select>
      {#if problem("question")}<span class="hint error">{problem("question")}</span>{/if}
    </div>
    {#if block.question}
      {@const all = columnsOf(block.question)}
      <fieldset class="plain">
        <legend>Columns printed</legend>
        {#each all as column (column.key)}
          <label class="check"><input type="checkbox" checked={!block.columns || block.columns.includes(column.key)}
            onchange={(e) => {
              if (block.kind !== "table") return;
              const shown = block.columns ?? all.map((c) => c.key);
              const next = e.currentTarget.checked ? all.map((c) => c.key).filter((k) => shown.includes(k) || k === column.key) : shown.filter((k) => k !== column.key);
              block.columns = next.length === all.length ? null : next;
            }} /> {column.label}</label>
        {/each}
        {#if problem("columns")}<p class="small error">{problem("columns")}</p>{/if}
      </fieldset>
    {/if}
    {@render text("caption", "Caption", block.caption, (v) => block.kind === "table" && (block.caption = v), "Printed as “Table 1. …”, numbered for you.")}
    {@render text("empty_text", "When there are no rows", block.empty_text, (v) => block.kind === "table" && (block.empty_text = v))}
  {:else if block.kind === "image"}
    <fieldset class="plain">
      <legend>Picture</legend>
      <label class="check"><input type="radio" name="{id}-source" value="template" bind:group={block.source} /> A file uploaded with the template</label>
      <label class="check"><input type="radio" name="{id}-source" value="question" bind:group={block.source} /> A photo the technician adds</label>
    </fieldset>
    {#if block.source === "template"}
      <div class="field">
        <label for="{id}-asset">Image</label>
        <select id="{id}-asset" class="input" value={block.asset ?? ""} onchange={(e) => block.kind === "image" && (block.asset = e.currentTarget.value || null)}>
          <option value="" disabled>{assets.length ? "Choose an image…" : "Upload one first"}</option>
          {#each assets.filter((a) => a.content_type.startsWith("image/")) as a (a.sha256)}<option value={a.sha256}>{a.name}</option>{/each}
        </select>
        {#if problem("asset")}<span class="hint error">{problem("asset")}</span>{/if}
      </div>
      <label class="button button-secondary small-button upload">
        <Upload size={14} aria-hidden="true" /> {uploading ? "Uploading…" : "Upload an image"}
        <input type="file" accept="image/png,image/jpeg,image/svg+xml" class="visually-hidden" onchange={upload} disabled={uploading} />
      </label>
      <span class="hint">PNG, JPEG or SVG, up to 4 MB. Photos lose their location data, and SVGs anything that isn't drawing.</span>
      {#if uploadError}<p class="small error">{uploadError}</p>{/if}
    {:else}
      <div class="field">
        <label for="{id}-photo">Photo question</label>
        <select id="{id}-photo" class="input" value={block.question ?? ""} onchange={(e) => block.kind === "image" && (block.question = e.currentTarget.value || null)}>
          <option value="" disabled>Choose a photo question…</option>
          {#each photos as q (q.id)}<option value={q.id}>{q.label}</option>{/each}
        </select>
        {#if problem("question")}<span class="hint error">{problem("question")}</span>{/if}
      </div>
    {/if}
    {@render text("caption", "Caption", block.caption, (v) => block.kind === "image" && (block.caption = v), "Printed as “Figure 1. …”, numbered for you.")}
    <div class="field">
      <label for="{id}-width">Width</label>
      <select id="{id}-width" class="input" bind:value={block.width}>
        <option value="full">The full width</option><option value="two_thirds">Two thirds</option><option value="half">Half</option><option value="third">A third</option>
      </select>
      <span class="hint">Never taller than about 40% of the page, however wide.</span>
    </div>
  {:else if block.kind === "gallery"}
    <div class="field">
      <label for="{id}-photo">Photos from</label>
      <select id="{id}-photo" class="input" value={block.question ?? ""} onchange={(e) => block.kind === "gallery" && (block.question = e.currentTarget.value || null)}>
        <option value="" disabled>Choose a photo question…</option>
        {#each photos as q (q.id)}<option value={q.id}>{q.label}</option>{/each}
      </select>
      {#if problem("question")}<span class="hint error">{problem("question")}</span>{/if}
    </div>
    <div class="field">
      <label for="{id}-per-row">Photos in a row</label>
      <select id="{id}-per-row" class="input" value={String(block.per_row)} onchange={(e) => block.kind === "gallery" && (block.per_row = Number(e.currentTarget.value) as 2 | 3)}>
        <option value="2">Two</option><option value="3">Three</option>
      </select>
    </div>
    {@render text("caption", "Caption", block.caption, (v) => block.kind === "gallery" && (block.caption = v))}
  {:else if block.kind === "callout"}
    <div class="field">
      <label for="{id}-tone">Tone</label>
      <select id="{id}-tone" class="input" bind:value={block.tone}>
        {#each TONES as tone (tone.value)}<option value={tone.value}>{tone.label}</option>{/each}
        <option value="custom">A colour of my own</option>
      </select>
      <span class="hint">The tones come from the report's style.</span>
    </div>
    {#if block.tone === "custom"}
      <div class="field">
        <label for="{id}-colour">Colour</label>
        <input id="{id}-colour" class="colour" type="color" value={block.colour ?? "#DCE6EE"} oninput={(e) => block.kind === "callout" && (block.colour = e.currentTarget.value.toUpperCase())} />
        {#if contrastNote}
          <span class="hint" class:error={contrastNote.low}>
            Text in {contrastNote.ink}: contrast {contrastNote.ratio.toFixed(1)}:1{contrastNote.low ? ", below the 4.5:1 that's easy to read. Choose a lighter or darker colour." : "."}
          </span>
        {:else if problem("colour")}<span class="hint error">{problem("colour")}</span>{/if}
      </div>
    {/if}
    <RuleField id="{id}-tone-rule" label="Tone set by the answers" bind:value={block.tone_rule} kind="value" expects="string" {engine} {entries}
      choices={TONES} problem={problem("tone_rule")} hint="The tone above, always." />
    {@render text("title", "Title", block.title, (v) => block.kind === "callout" && (block.title = v))}
    <RichTextEditor bind:value={() => block.kind === "callout" ? block.content : null, (v) => block.kind === "callout" && v && (block.content = v)} {entries} label="Text" id="{id}-content" />
  {:else if block.kind === "severity_summary"}
    <div class="field">
      <label for="{id}-question">Count the rows of</label>
      <select id="{id}-question" class="input" value={block.question ?? ""} onchange={(e) => { if (block.kind === "severity_summary") { block.question = e.currentTarget.value || null; block.column = null; } }}>
        <option value="" disabled>Choose a repeating group…</option>
        {#each lists as q (q.id)}<option value={q.id}>{q.label}</option>{/each}
      </select>
      {#if problem("question")}<span class="hint error">{problem("question")}</span>{/if}
    </div>
    {#if block.question}
      <div class="field">
        <label for="{id}-column">By the column</label>
        <select id="{id}-column" class="input" value={block.column ?? ""} onchange={(e) => block.kind === "severity_summary" && (block.column = e.currentTarget.value || null)}>
          <option value="" disabled>Choose a column…</option>
          {#each columnsOf(block.question) as c (c.key)}<option value={c.key}>{c.label}</option>{/each}
        </select>
        {#if problem("column")}<span class="hint error">{problem("column")}</span>{/if}
      </div>
    {/if}
    <div class="field">
      <label for="{id}-levels">Levels, in order</label>
      <input id="{id}-levels" class="input" value={block.levels.join(", ")}
        oninput={(e) => { if (block.kind === "severity_summary") { const levels = e.currentTarget.value.split(",").map((v) => v.trim()).filter(Boolean); if (levels.length) block.levels = levels.slice(0, 8); } }} />
      <span class="hint">Separated by commas. Rows count where the column says one of them.</span>
    </div>
    {@render text("caption", "Caption", block.caption, (v) => block.kind === "severity_summary" && (block.caption = v))}
  {:else if block.kind === "sources"}
    {@render text("intro", "Introduction", block.intro, (v) => block.kind === "sources" && (block.intro = v))}
    <fieldset class="plain">
      <legend>Sources every report gets</legend>
      {#each block.items as item, i (i)}
        <div class="pair">
          <input class="input" aria-label="Source {i + 1}: title" bind:value={item.title} maxlength="500" />
          <input class="input" aria-label="Source {i + 1}: link or reference" bind:value={item.link} maxlength="2000" />
          <button class="mini" type="button" aria-label="Remove source {i + 1}" onclick={() => block.kind === "sources" && block.items.splice(i, 1)}><X size={14} aria-hidden="true" /></button>
        </div>
      {/each}
      <button class="link-button small start" type="button" onclick={() => block.kind === "sources" && block.items.push({ title: "New source", link: "" })}><Plus size={14} aria-hidden="true" /> Add a source</button>
    </fieldset>
    <div class="field">
      <label for="{id}-own">The technician's own, from</label>
      <select id="{id}-own" class="input" value={block.question ?? ""} onchange={(e) => block.kind === "sources" && (block.question = e.currentTarget.value || null)}>
        <option value="">None</option>
        {#each lists as q (q.id)}<option value={q.id}>{q.label}</option>{/each}
      </select>
      <span class="hint" class:error={problem("question")}>{problem("question") ?? "A repeating group with title and link columns."}</span>
    </div>
  {:else if block.kind === "signatures"}
    <fieldset class="plain">
      <legend>Who signs</legend>
      {#each block.signers as signer, i (i)}
        <div class="signer">
          <select class="input" aria-label="Signature {i + 1}: who" value={signer.role} onchange={(e) => changeSigner(signer, e.currentTarget.value as Signer["role"])}>
            <option value="technician">The technician</option><option value="reviewer">The reviewer</option><option value="company">The company seal</option>
          </select>
          <select class="input" aria-label="Signature {i + 1}: how it looks" bind:value={signer.style}>
            <option value="handwritten">Handwritten</option><option value="stamp">A stamp</option>
          </select>
          <NameInput label="Signature {i + 1}: label" bind:value={signer.label} {entries} />
          <button class="mini" type="button" aria-label="Remove signature {i + 1}" disabled={block.signers.length === 1} onclick={() => block.kind === "signatures" && block.signers.splice(i, 1)}><X size={14} aria-hidden="true" /></button>
        </div>
      {/each}
      {#if block.signers.length < 4}
        <button class="link-button small start" type="button" onclick={() => block.kind === "signatures" && block.signers.push(nextSigner(block.signers))}><Plus size={14} aria-hidden="true" /> Add a signature</button>
      {/if}
    </fieldset>
    <div class="field">
      <label for="{id}-layout">Placed</label>
      <select id="{id}-layout" class="input" bind:value={block.layout}><option value="row">Side by side</option><option value="stack">Stacked</option></select>
    </div>
    <label class="check"><input type="checkbox" bind:checked={block.show_date} /> Print the date of signing</label>
    <p class="small muted">Who signs, and in what order, is the template's signing setting.</p>
  {:else if block.kind === "columns"}
    <div class="field">
      <label for="{id}-count">Columns</label>
      <select id="{id}-count" class="input" value={String(block.columns.length)}
        onchange={(e) => { if (block.kind !== "columns") return; const n = Number(e.currentTarget.value); block.columns = n > block.columns.length ? [...block.columns, []] : [block.columns[0], [...block.columns[1], ...block.columns[2] ?? []]]; }}>
        <option value="2">Two</option><option value="3">Three</option>
      </select>
      <span class="hint">Drag blocks into each column in the outline.</span>
    </div>
  {:else if block.kind === "page_break"}
    <p class="small muted">What follows starts on a new page. A page break never leaves an empty page.</p>
  {/if}
</section>

<section class="group" aria-labelledby="{id}-rules">
  <div class="group-head"><h3 id="{id}-rules">Rule</h3><Where builder /></div>
  <RuleField id="{id}-visible" label="Print only when" bind:value={block.visible_when} kind="condition" {engine} {entries}
    problem={problem("visible_when")} hint={block.kind === "section" ? "Always printed. A hidden section takes what's in it along." : "Always printed."} />
</section>

<style>
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--border);
  }
  .type {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    font-weight: 600;
  }
  .head-actions {
    display: flex;
  }
  .mini {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
  }
  .mini:hover:not(:disabled) {
    background: var(--surface-subtle);
    color: var(--text);
  }
  .mini:disabled {
    opacity: 0.35;
  }
  .group {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--border);
  }
  .group:last-child {
    border-bottom: 0;
  }
  .group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }
  .plain {
    display: grid;
    gap: var(--space-1);
    margin: 0;
    padding: 0;
    border: 0;
  }
  legend {
    margin-bottom: var(--space-1);
    font-size: 14px;
    font-weight: 600;
  }
  .pair,
  .signer {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
    gap: var(--space-1);
    align-items: center;
  }
  .signer {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
  .start,
  .small-button {
    justify-self: start;
  }
  .small-button {
    padding: 4px 10px;
    font-size: 13px;
  }
  .upload {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    cursor: pointer;
  }
  .colour {
    width: 64px;
    height: 36px;
    padding: 0;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: none;
  }
  .error {
    color: var(--critical-text);
  }
  p {
    margin: 0;
  }
</style>
