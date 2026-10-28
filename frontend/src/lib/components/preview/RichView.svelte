<script lang="ts">
  import type { RichNode } from "#lib/templates/types.js";
  import RichView from "./RichView.svelte";

  // Rich text as the PDF prints it, drawn as elements from its nodes, never as HTML,
  // so nothing in a template can add markup of its own.
  let { nodes }: { nodes: RichNode[] } = $props();

  const href = (node: RichNode) => {
    const link = node.marks?.find((m) => m.type === "link");
    const target = typeof link?.attrs?.href === "string" ? link.attrs.href : null;
    return target && /^(https?:\/\/|mailto:)/.test(target) ? target : null;
  };
  const has = (node: RichNode, mark: string) => node.marks?.some((m) => m.type === mark) ?? false;
</script>

{#snippet marked(node: RichNode, marks: string[])}
  {#if marks.length === 0}{node.text}
  {:else if marks[0] === "bold"}<strong>{@render marked(node, marks.slice(1))}</strong>
  {:else if marks[0] === "italic"}<em>{@render marked(node, marks.slice(1))}</em>
  {:else if marks[0] === "underline"}<u>{@render marked(node, marks.slice(1))}</u>
  {:else if marks[0] === "strike"}<s>{@render marked(node, marks.slice(1))}</s>
  {:else if marks[0] === "code"}<code>{@render marked(node, marks.slice(1))}</code>
  {:else}{@render marked(node, marks.slice(1))}{/if}
{/snippet}

{#each nodes as node, i (i)}
  {#if node.type === "paragraph"}
    <p><RichView nodes={node.content ?? []} /></p>
  {:else if node.type === "heading"}
    {#if node.attrs?.level === 4}<h4><RichView nodes={node.content ?? []} /></h4>{:else}<h3><RichView nodes={node.content ?? []} /></h3>{/if}
  {:else if node.type === "bulletList"}
    <ul><RichView nodes={node.content ?? []} /></ul>
  {:else if node.type === "orderedList"}
    <ol start={Number(node.attrs?.start ?? 1)}><RichView nodes={node.content ?? []} /></ol>
  {:else if node.type === "listItem"}
    <li><RichView nodes={node.content ?? []} /></li>
  {:else if node.type === "hardBreak"}
    <br />
  {:else if node.type === "text"}
    {@const link = href(node)}
    {@const marks = ["bold", "italic", "underline", "strike", "code"].filter((m) => has(node, m))}
    <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- links in a report go elsewhere: https and mailto only -->
    {#if link}<a href={link} rel="noopener noreferrer" target="_blank">{@render marked(node, marks)}</a>{:else}{@render marked(node, marks)}{/if}
  {/if}
{/each}
