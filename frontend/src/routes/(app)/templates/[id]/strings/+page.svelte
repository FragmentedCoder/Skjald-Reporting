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

  type Group = { id: string; name: string; rows: [string, string | RichText][] };

  // Each element's text, the form's and the PDF's apart, each in its order. Elements
  // that share a name (three sections called "New section") are numbered.
  const groups = $derived.by(() => {
    const list: Group[] = [];
    for (const [address, value] of found) {
      const id = address.split("/")[0];
      let group = list.find((g) => g.id === id);
      if (!group) list.push((group = { id, name: elements[id] ?? id, rows: [] }));
      group.rows.push([address, value]);
    }
    const counts: Record<string, number> = {};
    for (const g of list) counts[g.name] = (counts[g.name] ?? 0) + 1;
    const seen: Record<string, number> = {};
    for (const g of list) {
      if (counts[g.name] < 2) continue;
      seen[g.name] = (seen[g.name] ?? 0) + 1;
      g.name = `${g.name} (${seen[g.name]})`;
    }
    const blocks = new Set(blocksOf(content.layout).map((b) => b.id));
    return { form: list.filter((g) => !blocks.has(g.id)), pdf: list.filter((g) => blocks.has(g.id)) };
  });

  function set(address: string, value: string | RichText | null) {
    if (value === null || draft.readonly) return;
    apply(content, { [address]: value });
  }
</script>

{#if draft.readonly}
  <p class="alert alert-info small">This version is published and can't change. Start a new draft on the Versions tab to change its text.</p>
{/if}

{#snippet element(group: Group)}
  <section class="section" aria-label={group.name}>
    <h3 class="section-title">{group.name}</h3>
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
          {:else if draft.readonly}
            <span class="label">{field(address)}</span>
            <p class="small muted">Rich text: shown with the published version.</p>
          {:else}
            <!-- The editor shows its label itself. -->
            <RichTextEditor bind:value={() => value as RichText, (v) => set(address, v)} {entries} label={field(address)} id="str-{address}" />
          {/if}
        </div>
      {/each}
    </div>
  </section>
{/snippet}

<div class="strings">
  <p class="small muted intro">Every piece of text in the template, element by element: what the technician reads on the form and what's printed in the PDF. To translate a template, copy it for translation on the Templates page and change its text here. Leave names in {"{{ }}"} as they are.</p>
  <!-- The form beside the PDF where the window is wide enough, each in its own order. -->
  <div class="sides">
    <div class="side">
      <h2 class="side-title">The technician's form <Where form /></h2>
      {#each groups.form as group (group.id)}{@render element(group)}{:else}<p class="small muted">No text on the form yet.</p>{/each}
    </div>
    <div class="side">
      <h2 class="side-title">The PDF <Where pdf /></h2>
      {#each groups.pdf as group (group.id)}{@render element(group)}{:else}<p class="small muted">No text in the PDF yet.</p>{/each}
    </div>
  </div>
</div>

<style>
  .strings {
    display: grid;
    gap: var(--space-4);
    margin-top: var(--space-4);
  }
  .intro {
    max-width: 960px;
    margin: 0;
  }
  .sides {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 520px), 1fr));
    gap: var(--space-4);
    align-items: start;
  }
  .side {
    display: grid;
    gap: var(--space-2);
  }
  .side-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
    font: var(--type-subheading);
  }
  .label {
    font-weight: 500;
  }
</style>
