<script lang="ts">
  import { onDestroy } from "svelte";
  import { CelClient } from "#lib/cel/client.js";
  import { Engine, ExpressionError, human, plain } from "#lib/cel/engine.js";
  import { FUNCTIONS } from "#lib/cel/library.js";
  import Where from "#lib/components/builder/Where.svelte";
  import { entryName } from "#lib/library.js";
  import { catalogue } from "#lib/templates/catalogue.js";
  import { useDraft } from "#lib/templates/draft.svelte.js";
  import { LivePreview } from "#lib/templates/live.svelte.js";
  import { CONTEXT_GROUPS, declarations } from "#lib/templates/names.js";
  import type { TemplateContent } from "#lib/templates/types.js";

  // The Data tab: every name the template can read, what it is, where it comes from
  // and an example; a reference for every function, with its examples worked out;
  // and a box to try an expression on the sample answers.
  const draft = useDraft();
  const content = $derived(draft.content as TemplateContent);
  const entries = $derived(catalogue(content, draft.libraryNames, draft.libraryLabels));
  const answers = $derived(entries.filter((e) => e.group === "Answers"));
  const custom = $derived(entries.filter((e) => e.name.startsWith("customer.custom.") || e.name.startsWith("project.custom.")));
  const names = $derived(JSON.stringify(declarations(content, draft.libraryNames)));

  const live = new LivePreview();
  // What's typed in the box runs in the expression worker, with its time limit.
  const worker = new CelClient();
  onDestroy(() => {
    live.close();
    worker.close();
  });
  $effect(() => {
    const snapshot = $state.snapshot(content) as TemplateContent;
    live.update({ content: snapshot, answers: snapshot.sample.answers, context: draft.sampleContext, assets: {}, library: draft.libraryPreview });
  });

  const values = $derived({ ...draft.sampleContext, ...draft.libraryPreview.values, answers: live.model?.values ?? {} });

  function show(value: unknown): string {
    const v = plain(value);
    if (v === null || v === undefined || v === "") return "—";
    if (v instanceof Date) return v.toISOString().replace(".000Z", "Z");
    return typeof v === "string" ? `"${v}"` : JSON.stringify(v);
  }

  function lookup(name: string): unknown {
    let current: unknown = values;
    for (const part of name.split(".")) current = current && typeof current === "object" ? (current as Record<string, unknown>)[part] : undefined;
    return current;
  }

  const examples = new Engine({});
  function example(expr: string): string {
    try {
      return show(examples.evaluateRaw(expr, {}));
    } catch (error) {
      return error instanceof ExpressionError ? error.message : String(error);
    }
  }

  let trying = $state('report.number + " for " + customer.name');
  let tried = $state<{ ok: boolean; text: string }>({ ok: true, text: "" });
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const expr = trying;
    const tables = draft.libraryPreview.tables;
    const setup = { key: `${names}|${content.settings.language}|${JSON.stringify(tables)}`, declarations: JSON.parse(names), options: { language: content.settings.language, tables } };
    const now = $state.snapshot(values) as Record<string, unknown>;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!expr.trim()) {
        tried = { ok: true, text: "" };
        return;
      }
      const [checked, result] = await worker.run(setup, now, [{ kind: "check", expr }, { kind: "evaluate", expr }]);
      if (!checked.ok) tried = { ok: false, text: checked.message };
      else if (!result.ok) tried = { ok: false, text: result.message };
      else tried = { ok: true, text: `${show(result.value)}, which is ${human(String(checked.value))}` };
    }, 200);
  });

  const groups = [...new Set(FUNCTIONS.map((f) => f.group))];
</script>

<div class="data">
  <section class="section" aria-labelledby="try-title">
    <h2 id="try-title" class="section-title">Try an expression <Where builder /></h2>
    <p class="small muted">Worked out on the sample answers, the way rules and text in {"{{ }}"} are.</p>
    <label class="visually-hidden" for="try-expression">Expression</label>
    <textarea id="try-expression" class="input mono" rows="2" spellcheck="false" bind:value={trying}></textarea>
    <p class="result" class:error={!tried.ok} role="status">{tried.text}</p>
  </section>

  <!-- The names, in two columns where the window is wide enough. -->
  <div class="reference">
  <section class="section" aria-labelledby="answers-title">
    <h2 id="answers-title" class="section-title">Answers <Where form /></h2>
    <p class="small muted">What the technician fills in, by each question's variable name. Calculated values are worked out from the others.</p>
    {#if answers.length}
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Name</th><th>Question</th><th>Kind</th><th>Sample</th></tr></thead>
          <tbody>
            {#each answers as entry (entry.name)}
              <tr><td class="mono">{entry.name}</td><td>{entry.label}</td><td>{human(entry.type)}</td><td class="mono sample">{show(lookup(entry.name))}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="small muted">No questions yet: add them on the Questions tab.</p>
    {/if}
  </section>

  {#each CONTEXT_GROUPS as group (group.name)}
    <section class="section" aria-labelledby="group-{group.name}">
      <h2 id="group-{group.name}" class="section-title">{group.label}</h2>
      <p class="small muted">{group.source}.</p>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Name</th><th>What it is</th><th>Kind</th><th>Example</th></tr></thead>
          <tbody>
            {#each group.names as n (n.name)}
              <tr><td class="mono">{n.name}</td><td>{n.description}</td><td>{human(n.type)}</td><td class="mono sample">{show(n.example)}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {/each}

  {#if custom.length}
    <section class="section" aria-labelledby="custom-title">
      <h2 id="custom-title" class="section-title">Custom fields</h2>
      <p class="small muted">The company's own details about customers and projects, filled in on their forms and set up under Custom fields. The examples are made up.</p>
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Name</th><th>What it is</th><th>Kind</th><th>Example</th></tr></thead>
          <tbody>
            {#each custom as entry (entry.name)}
              <tr><td class="mono">{entry.name}</td><td>{entry.label}</td><td>{human(entry.type)}</td><td class="mono sample">{show(lookup(entry.name))}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {/if}

  <section class="section" aria-labelledby="library-title">
    <h2 id="library-title" class="section-title">Shared library</h2>
    <p class="small muted">Shared by every template and report, and changed in the Library. A report uses the current values until it's signed, then keeps those.</p>
    {#if draft.library.length}
      <div class="table-wrap">
        <table class="table">
          <thead><tr><th>Name</th><th>What it is</th><th>Value</th></tr></thead>
          <tbody>
            {#each draft.library as entry (entry.id)}
              <tr>
                <td class="mono">{entryName(entry)}</td>
                <td>{entry.description || "—"}</td>
                <td class="sample">{"value" in entry.value ? entry.value.value : "text" in entry.value ? entry.value.text : `${Object.keys(entry.value.rows).length} rows, columns ${entry.value.columns.join(", ")}`}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="small muted">The library is empty.</p>
    {/if}
  </section>

  </div>

  <section class="section" aria-labelledby="functions-title">
    <h2 id="functions-title" class="section-title">Functions</h2>
    <p class="small muted">What expressions can call. Each example is worked out here, by the same engine the form uses.</p>
    {#each groups as group (group)}
      <h3 class="group">{group}</h3>
      <dl class="functions">
        {#each FUNCTIONS.filter((f) => f.group === group) as f (f.name)}
          <div class="function">
            <dt>
              <span class="mono name">{f.name}</span>
              {#each f.overloads as o (o.id)}<span class="mono small signature">{o.signature}</span>{/each}
            </dt>
            <dd>
              <p>{f.summary}</p>
              {#each f.examples as ex, i (i)}<p class="small"><span class="mono">{ex.expr}</span> gives <span class="mono">{example(ex.expr)}</span></p>{/each}
            </dd>
          </div>
        {/each}
      </dl>
    {/each}
  </section>
</div>

<style>
  .data {
    display: grid;
    gap: var(--space-2);
    margin-top: var(--space-4);
  }
  .reference {
    columns: 2 560px;
    column-gap: var(--space-2);
  }
  .reference > .section {
    margin: 0 0 var(--space-2);
    break-inside: avoid;
  }
  .section-title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  textarea {
    width: 100%;
    font-size: 13px;
  }
  .result {
    min-height: 1.5em;
    margin: var(--space-2) 0 0;
    font-family: var(--font-mono);
    font-size: 13px;
  }
  .error {
    color: var(--critical-text);
    font-family: inherit;
  }
  .sample {
    max-width: 280px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .group {
    margin: var(--space-4) 0 var(--space-2);
    font-size: 15px;
    font-weight: 600;
  }
  .functions {
    display: grid;
    gap: var(--space-3);
    margin: 0;
  }
  .function {
    display: grid;
    grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.4fr);
    gap: var(--space-4);
    padding-bottom: var(--space-3);
    border-bottom: 1px solid var(--border);
  }
  dt {
    display: grid;
    align-content: start;
    gap: 2px;
  }
  .name {
    font-weight: 600;
  }
  .signature {
    color: var(--text-muted);
    overflow-wrap: anywhere;
  }
  dd {
    margin: 0;
  }
  dd p {
    margin: 0 0 var(--space-1);
  }
  @media (max-width: 720px) {
    .function {
      grid-template-columns: 1fr;
      gap: var(--space-1);
    }
  }
</style>
