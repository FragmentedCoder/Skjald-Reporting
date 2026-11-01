<script lang="ts">
  import { Engine, ExpressionError } from "#lib/cel/engine.js";
  import { FUNCTIONS } from "#lib/cel/library.js";
  import { shown } from "#lib/templates/nameGroups.js";

  // Every function expressions can call, with each example worked out here by the
  // same engine the form uses.
  const examples = new Engine({});
  function example(expr: string): string {
    try {
      return shown(examples.evaluateRaw(expr, {}));
    } catch (error) {
      return error instanceof ExpressionError ? error.message : String(error);
    }
  }

  const groups = [...new Set(FUNCTIONS.map((f) => f.group))];
</script>

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

<style>
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
