<script lang="ts">
  import type { Editor, JSONContent } from "@tiptap/core";
  import Bold from "@lucide/svelte/icons/bold";
  import Braces from "@lucide/svelte/icons/braces";
  import Italic from "@lucide/svelte/icons/italic";
  import LinkIcon from "@lucide/svelte/icons/link";
  import List from "@lucide/svelte/icons/list";
  import ListOrdered from "@lucide/svelte/icons/list-ordered";
  import Underline from "@lucide/svelte/icons/underline";
  import { onMount } from "svelte";
  import type { NameEntry } from "#lib/templates/catalogue.js";
  import { makeEditor } from "#lib/templates/editor.js";
  import type { RichText } from "#lib/templates/types.js";

  // Rich text for the PDF: formatting, lists, links, and names whose value is printed
  // where they sit (shown as {{ answers.summary }} chips).
  let { value = $bindable(), entries, label, id }: {
    value: RichText | null;
    entries: NameEntry[];
    label: string;
    id: string;
  } = $props();

  let element = $state<HTMLDivElement>();
  let editor = $state<Editor | null>(null);
  // Bumped on every change, so the buttons show what's on where the cursor is.
  let changes = $state(0);
  let written = "";

  let linking = $state(false);
  let address = $state("");
  let naming = $state(false);
  let expression = $state("");

  onMount(() => {
    if (!element) return;
    editor = makeEditor(element, (value ?? { type: "doc", content: [] }) as JSONContent, label, (doc) => {
      written = JSON.stringify(doc);
      value = doc as RichText;
    });
    editor.on("transaction", () => changes++);
    written = JSON.stringify(editor.getJSON());
    return () => editor?.destroy();
  });

  // Changes from elsewhere (a rename, a reload) reach the editor.
  $effect(() => {
    const text = JSON.stringify(value);
    if (editor && text !== written && value) {
      written = text;
      editor.commands.setContent(value as JSONContent, { emitUpdate: false });
    }
  });

  const on = (name: string, attrs?: Record<string, unknown>) => {
    void changes;
    return editor?.isActive(name, attrs) ?? false;
  };

  function insertName(expr: string) {
    if (!expr.trim()) return;
    editor?.chain().focus().insertContent({ type: "variable", attrs: { expr: expr.trim() } }).run();
    naming = false;
    expression = "";
  }

  function setLink() {
    const href = address.trim();
    if (!href) editor?.chain().focus().unsetLink().run();
    else if (/^(https?:\/\/|mailto:)/.test(href)) editor?.chain().focus().extendMarkRange("link").setLink({ href }).run();
    linking = false;
  }

  const printable = $derived(entries.filter((e) => e.shape !== "rows" && e.shape !== "other"));
  const groups = $derived([...new Set(printable.map((e) => e.group))]);
</script>

<div class="rich" role="group" aria-labelledby="{id}-label">
  <span id="{id}-label" class="label">{label}</span>
  <!-- Pressing a button leaves the cursor, and what's selected, in the text. -->
  <div class="toolbar" role="toolbar" aria-label="{label}: formatting" tabindex="-1" onmousedown={(e) => e.preventDefault()}>
    <button type="button" aria-label="Bold" title="Bold" aria-pressed={on("bold")} onclick={() => editor?.chain().focus().toggleBold().run()}><Bold size={15} aria-hidden="true" /></button>
    <button type="button" aria-label="Italic" title="Italic" aria-pressed={on("italic")} onclick={() => editor?.chain().focus().toggleItalic().run()}><Italic size={15} aria-hidden="true" /></button>
    <button type="button" aria-label="Underline" title="Underline" aria-pressed={on("underline")} onclick={() => editor?.chain().focus().toggleUnderline().run()}><Underline size={15} aria-hidden="true" /></button>
    <span class="divider"></span>
    <button type="button" class="text" aria-pressed={on("heading", { level: 3 })} onclick={() => editor?.chain().focus().toggleHeading({ level: 3 }).run()}>Heading</button>
    <button type="button" aria-label="Bulleted list" title="Bulleted list" aria-pressed={on("bulletList")} onclick={() => editor?.chain().focus().toggleBulletList().run()}><List size={15} aria-hidden="true" /></button>
    <button type="button" aria-label="Numbered list" title="Numbered list" aria-pressed={on("orderedList")} onclick={() => editor?.chain().focus().toggleOrderedList().run()}><ListOrdered size={15} aria-hidden="true" /></button>
    <button type="button" aria-label="Link" title="Link" aria-pressed={on("link")}
      onclick={() => { address = String(editor?.getAttributes("link").href ?? ""); linking = !linking; naming = false; }}><LinkIcon size={15} aria-hidden="true" /></button>
    <span class="divider"></span>
    <button type="button" class="text" aria-expanded={naming} onclick={() => { naming = !naming; linking = false; }}><Braces size={15} aria-hidden="true" /> Insert a name</button>
  </div>
  {#if linking}
    <form class="popover" onsubmit={(e) => { e.preventDefault(); setLink(); }}>
      <input class="input" aria-label="Link address" placeholder="https://" bind:value={address} />
      <button class="button button-secondary" type="submit">{address.trim() ? "Set link" : "Remove link"}</button>
    </form>
  {/if}
  {#if naming}
    <div class="popover">
      <select class="input" aria-label="Name to insert" onchange={(e) => insertName(e.currentTarget.value)}>
        <option value="">Choose a name…</option>
        {#each groups as group (group)}
          <optgroup label={group}>{#each printable.filter((e) => e.group === group) as e (e.name)}<option value={e.name}>{e.label}</option>{/each}</optgroup>
        {/each}
      </select>
      <form class="expression" onsubmit={(e) => { e.preventDefault(); insertName(expression); }}>
        <input class="input mono" aria-label="Or an expression" placeholder='format_date(answers.detected, "d MMMM yyyy")' bind:value={expression} />
        <button class="button button-secondary" type="submit" disabled={!expression.trim()}>Insert</button>
      </form>
    </div>
  {/if}
  <div class="surface" bind:this={element}></div>
</div>

<style>
  .rich {
    display: grid;
    gap: var(--space-1);
  }
  .label {
    font-size: 14px;
    font-weight: 600;
  }
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 2px;
  }
  .toolbar button {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 28px;
    min-width: 28px;
    justify-content: center;
    padding: 0 6px;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text);
    font-size: 13px;
    cursor: pointer;
  }
  .toolbar button:hover {
    border-color: var(--border);
  }
  .toolbar button[aria-pressed="true"] {
    background: var(--surface-subtle);
    border-color: var(--border-strong);
  }
  .divider {
    width: 1px;
    height: 18px;
    margin: 0 4px;
    background: var(--border);
  }
  .popover,
  .expression {
    display: flex;
    gap: var(--space-1);
  }
  .popover {
    flex-direction: column;
  }
  .expression .input,
  form.popover .input {
    flex: 1;
    min-width: 0;
  }
  form.popover {
    flex-direction: row;
  }
  .surface :global(.rich-input) {
    min-height: 90px;
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--text);
    white-space: pre-wrap;
    word-wrap: break-word;
    outline: none;
  }
  .surface :global(.rich-input:focus-visible) {
    border-color: var(--link);
    box-shadow: 0 0 0 1px var(--link);
  }
  .surface :global(.rich-input p) {
    margin: 0 0 0.5em;
  }
  .surface :global(.rich-input h3),
  .surface :global(.rich-input h4) {
    margin: 0.4em 0;
    font-family: var(--font-display);
    font-weight: 400;
  }
  .surface :global(.rich-input ul),
  .surface :global(.rich-input ol) {
    margin: 0 0 0.5em;
    padding-left: 1.4em;
  }
  .surface :global(span.variable) {
    padding: 1px 6px;
    border-radius: var(--radius-pill);
    background: var(--info-bg);
    color: var(--info-text);
    font-family: var(--font-mono);
    font-size: 12px;
    white-space: nowrap;
  }
  .surface :global(.ProseMirror-selectednode) {
    outline: 2px solid var(--link);
  }
</style>
