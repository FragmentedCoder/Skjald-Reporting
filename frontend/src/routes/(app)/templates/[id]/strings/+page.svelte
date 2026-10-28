<script lang="ts">
  import RichTextEditor from "#lib/components/builder/RichTextEditor.svelte";
  import Where from "#lib/components/builder/Where.svelte";
  import { catalogue } from "#lib/templates/catalogue.js";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import { apply, strings } from "#lib/templates/strings.js";
  import { questionsOf, type Block, type RichText, type TemplateContent } from "#lib/templates/types.js";

  // The Strings view: every piece of text in the template on one page, element by
  // element, to translate a copy (Templates → Copy for translation) or check the wording.
  // Names in {{ }} are left as they are; they're filled in when the report is written.
  const draft = useDraft();
  const content = $derived(draft.content as TemplateContent);
  const entries = $derived(catalogue(content, draft.libraryNames, draft.libraryLabels));
  const found = $derived(Object.entries(strings(content)));

  const FIELDS: Record<string, string> = {
    title: "Title",
    subtitle: "Subtitle",
    label: "Label",
    help: "Help",
    valid_message: "Message when the answer isn't valid",
    text: "Text",
    caption: "Caption",
    empty_text: "Text when there are no rows",
    intro: "Introduction",
    placeholder: "Placeholder",
    pattern_message: "Message when the pattern doesn't match",
    unit: "Unit",
    yes_label: "Yes",
    no_label: "No",
    content: "Text",
    value: "Value",
  };
  const LISTS: Record<string, string> = { options: "Option", columns: "Column", facts: "Fact", items: "Source", signers: "Signer" };

  function blocksOf(blocks: Block[]): Block[] {
    return blocks.flatMap((b) => [b, ...("blocks" in b ? blocksOf(b.blocks) : []), ...("columns" in b && Array.isArray(b.columns) ? b.columns.flatMap((c) => (Array.isArray(c) ? blocksOf(c as Block[]) : [])) : [])]);
  }

  // What each element is, by ID: a step, a question or a block.
  const elements = $derived.by(() => {
    const names: Record<string, string> = {};
    for (const step of content.form) names[step.id] = `Step “${step.title}”`;
    for (const q of questionsOf(content)) names[q.id] = `Question “${q.label}”`;
    for (const b of blocksOf(content.layout)) {
      const title = "title" in b && typeof b.title === "string" ? b.title : "text" in b && typeof b.text === "string" ? b.text : "";
      names[b.id] = `${b.kind.replace("_", " ").replace(/^./, (c) => c.toUpperCase())} block${title ? ` “${title}”` : ""}`;
    }
    return names;
  });

  function field(address: string): string {
    const parts = address.split("/").slice(1);
    const words: string[] = [];
    for (let i = 0; i < parts.length; i++) {
      if (LISTS[parts[i]] && /^\d+$/.test(parts[i + 1] ?? "")) {
        words.push(`${LISTS[parts[i]]} ${Number(parts[i + 1]) + 1}`);
        i++;
      }
    }
    const last = parts.at(-1) ?? "";
    return [...words, FIELDS[last] ?? last].join(": ");
  }

  const groups = $derived.by(() => {
    const list: { id: string; name: string; rows: [string, string | RichText][] }[] = [];
    for (const [address, value] of found) {
      const id = address.split("/")[0];
      let group = list.find((g) => g.id === id);
      if (!group) list.push((group = { id, name: elements[id] ?? id, rows: [] }));
      group.rows.push([address, value]);
    }
    return list;
  });

  function set(address: string, value: string | RichText | null) {
    if (value === null || draft.readonly) return;
    apply(content, { [address]: value });
  }
</script>

{#if draft.readonly}
  <p class="alert alert-info small">This version is published and can't change. Start a new draft on the Versions tab to change its text.</p>
{/if}

<div class="strings">
  <p class="small muted">Every piece of text in the template, element by element: what the technician reads on the form <Where form /> and what's printed in the PDF <Where pdf />. To translate a template, copy it for translation on the Templates page and change its text here. Leave names in {"{{ }}"} as they are.</p>
  {#each groups as group (group.id)}
    <section class="section" aria-label={group.name}>
      <h2 class="section-title">{group.name}</h2>
      <div class="stack">
        {#each group.rows as [address, value] (address)}
          <div class="field">
            {#if typeof value === "string"}
              <label for="str-{address}">{field(address)}</label>
              {#if value.length > 80 || field(address) === "Help"}
                <textarea id="str-{address}" class="input" rows="2" {value} disabled={draft.readonly} onchange={(e) => set(address, e.currentTarget.value)}></textarea>
              {:else}
                <input id="str-{address}" class="input" {value} disabled={draft.readonly} onchange={(e) => set(address, e.currentTarget.value)} />
              {/if}
            {:else}
              <span class="label">{field(address)}</span>
              {#if draft.readonly}
                <p class="small muted">Rich text: shown with the published version.</p>
              {:else}
                <RichTextEditor bind:value={() => value as RichText, (v) => set(address, v)} {entries} label={`${group.name}: ${field(address)}`} id="str-{address}" />
              {/if}
            {/if}
          </div>
        {/each}
      </div>
    </section>
  {:else}
    <p class="muted">No text yet.</p>
  {/each}
</div>

<style>
  /* Element by element, in two columns where the window is wide enough. */
  .strings {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 560px), 1fr));
    gap: var(--space-4);
    align-items: start;
  }
  .strings > p {
    grid-column: 1 / -1;
    max-width: 960px;
  }
  .label {
    font-weight: 500;
  }
</style>
