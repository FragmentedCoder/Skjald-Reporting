<script lang="ts">
  import { onDestroy } from "svelte";
  import Where from "#lib/components/builder/Where.svelte";
  import AnswerField from "#lib/components/form/AnswerField.svelte";
  import PdfPages from "#lib/components/preview/PdfPages.svelte";
  import { checkAnswer } from "#lib/templates/answers.js";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import { fieldType, settingsOf } from "#lib/templates/fields.js";
  import { LivePreview } from "#lib/templates/live.svelte.js";
  import { sampleContext } from "#lib/templates/preview.js";
  import type { Question, TemplateContent } from "#lib/templates/types.js";

  // "Try it": the technician's screen for the draft, one step at a time, with the PDF
  // beside it changing as the answers do. The answers are the template's sample
  // answers, kept with the draft; photos, files and signatures stay in this browser.
  const draft = useDraft();
  const content = $derived(draft.content as TemplateContent);
  const LOCAL = new Set(["photo", "file", "signature"]);
  let local = $state<Record<string, unknown>>({});

  const live = new LivePreview();
  onDestroy(() => live.close());
  $effect(() => {
    const snapshot = $state.snapshot(content) as TemplateContent;
    const answers = { ...snapshot.sample.answers, ...($state.snapshot(local) as Record<string, unknown>) };
    const assets = Object.fromEntries((draft.template?.assets ?? []).map((a) => [a.sha256, { url: a.url, width: a.width, height: a.height }]));
    live.update({ content: snapshot, answers, context: sampleContext(), assets });
  });

  const model = $derived(live.model);
  const hidden = $derived(new Set(model?.formHidden ?? []));
  const required = $derived(new Set(model?.formRequired ?? []));
  const invalid = $derived(new Map((model?.invalid ?? []).map((i) => [i.id, i.message])));
  const steps = $derived(content.form.filter((s) => !hidden.has(s.id)));
  let current = $state(0);
  const step = $derived(steps[Math.min(current, steps.length - 1)]);

  function answer(q: Question): unknown {
    return LOCAL.has(q.type) ? local[q.id] : content.sample.answers[q.id];
  }

  function set(q: Question, value: unknown) {
    const blank = value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length);
    if (LOCAL.has(q.type)) {
      if (blank) delete local[q.id];
      else local[q.id] = value;
    } else if (blank) {
      delete content.sample.answers[q.id];
    } else {
      content.sample.answers[q.id] = value;
    }
  }

  // Everything that would keep the report from going for review.
  let checked = $state(false);
  const missing = $derived.by(() => {
    const found: { step: number; question: Question; message: string }[] = [];
    steps.forEach((s, i) => {
      for (const q of s.questions) {
        if (hidden.has(q.id) || !fieldType(q.type).asks || q.type === "calculated") continue;
        const value = answer(q);
        const empty = value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length);
        const vector = q.type === "cvss" ? (value as { vector?: string } | undefined)?.vector : value;
        const typed = empty ? null : checkAnswer(q.type, settingsOf(q.type, q.settings), vector);
        const message = typed ?? invalid.get(q.id) ?? (required.has(q.id) && empty ? "is required." : null);
        if (message) found.push({ step: i, question: q, message });
      }
    });
    return found;
  });

  function reset() {
    content.sample.answers = {};
    local = {};
    current = 0;
    checked = false;
  }
</script>

{#if draft.readonly}
  <p class="alert alert-info small">This is version {draft.shownVersion}. The answers here aren't kept; choose Edit to change the sample answers with the template.</p>
{/if}

<div class="try">
  <section class="form" aria-labelledby="form-heading">
    <div class="intro">
      <h2 id="form-heading" class="section-title">The technician's form <Where form /></h2>
      <p class="small muted">The draft as technicians will see it. These answers are the template's sample answers, kept with the draft.</p>
    </div>

    <ol class="progress" aria-label="Steps">
      {#each steps as s, i (s.id)}
        <li><button type="button" aria-current={i === current ? "step" : undefined} onclick={() => (current = i)}>
          <span class="n">{i + 1}</span> {s.title}
          {#if checked && missing.some((m) => m.step === i)}<span class="flag" aria-label="has something to fix">!</span>{/if}
        </button></li>
      {/each}
    </ol>

    {#if step}
      <div class="step">
        <h3 class="step-title">{step.title}</h3>
        {#if step.help}<p class="small muted">{step.help}</p>{/if}
        {#each step.questions as q (q.id)}
          {#if !(q.type === "calculated" && !q.settings.show_in_form)}
            <AnswerField question={q} bind:value={() => answer(q), (v) => set(q, v)} required={required.has(q.id)}
              hidden={hidden.has(q.id)} invalid={invalid.get(q.id) ?? null} computed={q.key ? model?.values[q.key] : undefined} />
          {/if}
        {:else}
          <p class="small muted">This step has no questions yet.</p>
        {/each}
      </div>
      <div class="button-row">
        <button class="button button-secondary" type="button" disabled={current === 0} onclick={() => current--}>Back</button>
        {#if current < steps.length - 1}
          <button class="button button-primary" type="button" onclick={() => current++}>Next</button>
        {:else}
          <button class="button button-primary" type="button" onclick={() => (checked = true)}>Check the answers</button>
        {/if}
        <button class="link-button small reset" type="button" onclick={reset}>Clear the answers</button>
      </div>
    {:else}
      <p class="small muted">The form has no steps to show: add questions on the Questions tab.</p>
    {/if}

    {#if checked}
      <section class="review" aria-labelledby="review-heading">
        <h3 id="review-heading">Before it can go for review</h3>
        {#if missing.length}
          <ul>
            {#each missing as m (m.question.id)}
              <li><button class="link-button" type="button" onclick={() => (current = m.step)}>{m.question.label}</button> {m.message}</li>
            {/each}
          </ul>
        {:else}
          <p class="small">Nothing missing: a report like this could go for review.</p>
        {/if}
      </section>
    {/if}
  </section>

  <section class="pdf" aria-labelledby="pdf-heading">
    <h2 id="pdf-heading" class="section-title">The PDF <Where pdf /></h2>
    {#if live.problem}<p class="alert alert-warning small">{live.problem}</p>{/if}
    {#if live.paged}
      <PdfPages paged={live.paged} classification={String(sampleContext().project.classification)} />
    {:else}
      <p class="muted">Working out the pages…</p>
    {/if}
  </section>
</div>

<style>
  .try {
    display: grid;
    grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr);
    gap: var(--space-6);
    align-items: start;
    margin-top: var(--space-4);
  }
  .section-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .intro p {
    margin: var(--space-1) 0 var(--space-3);
  }
  .progress {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    margin: 0 0 var(--space-3);
    padding: 0;
    list-style: none;
  }
  .progress button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    background: var(--surface);
    color: var(--text-muted);
    font-size: 13px;
    cursor: pointer;
  }
  .progress button[aria-current="step"] {
    border-color: var(--link);
    color: var(--text);
    font-weight: 600;
  }
  .n {
    display: inline-grid;
    place-items: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--surface-subtle);
    font-size: 12px;
  }
  .flag {
    color: var(--critical-text);
    font-weight: 700;
  }
  .step {
    display: grid;
    gap: var(--space-4);
    padding: var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
  }
  .step-title {
    margin: 0;
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 400;
  }
  .step > p {
    margin: calc(-1 * var(--space-3)) 0 0;
  }
  .button-row {
    align-items: center;
    margin-top: var(--space-3);
  }
  .reset {
    margin-left: auto;
  }
  .review {
    margin-top: var(--space-4);
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--surface);
  }
  .review h3 {
    margin: 0 0 var(--space-2);
    font-size: 15px;
  }
  .review ul {
    margin: 0;
    padding-left: var(--space-4);
  }
  .pdf {
    position: sticky;
    top: var(--space-4);
    max-height: calc(100vh - 2 * var(--space-4));
    overflow-y: auto;
  }
  @media (max-width: 1100px) {
    .try {
      grid-template-columns: minmax(0, 1fr);
    }
    .pdf {
      position: static;
      max-height: none;
    }
  }
</style>
