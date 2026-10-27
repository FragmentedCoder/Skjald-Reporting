<script lang="ts">
  import { blocksOf, questionsOf, type Problem, type TemplateContent } from "#lib/templates/types.js";

  // Every problem that keeps the draft from being published, each with a button that
  // selects what it's about.
  let { problems, content, onselect }: {
    problems: Problem[];
    content: TemplateContent;
    onselect: (problem: Problem) => void;
  } = $props();

  const names = $derived.by(() => {
    const found: Record<string, string> = {};
    content.form.forEach((step, i) => (found[step.id] = `Step ${i + 1}: ${step.title}`));
    for (const q of questionsOf(content)) found[q.id] = q.label;
    for (const b of blocksOf(content.layout)) {
      const title = "title" in b && b.title ? b.title : "text" in b && typeof b.text === "string" ? b.text : b.kind.replace("_", " ");
      found[b.id] = String(title);
    }
    return found;
  });
</script>

<section id="problems" class="problems" aria-labelledby="problems-title" tabindex="-1">
  <h2 id="problems-title" class="section-title">Problems</h2>
  {#if problems.length}
    <p class="small muted">Fix these before publishing. The draft is saved as it is meanwhile.</p>
    <ul>
      {#each problems as problem, i (i)}
        <li>
          <button class="link-button" type="button" onclick={() => onselect(problem)}>{names[problem.element] ?? problem.element}</button>
          <span>{problem.message}</span>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="small muted">None: this draft can be published.</p>
  {/if}
</section>

<style>
  .problems {
    margin-top: var(--space-8);
    padding: var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  ul {
    display: grid;
    gap: var(--space-2);
    margin: var(--space-2) 0 0;
    padding: 0;
    list-style: none;
  }
  li {
    display: grid;
    grid-template-columns: minmax(120px, 0.35fr) 1fr;
    gap: var(--space-3);
    font-size: 14px;
  }
  li button {
    text-align: left;
  }
  @media (max-width: 640px) {
    li {
      grid-template-columns: 1fr;
      gap: 0;
    }
  }
</style>
