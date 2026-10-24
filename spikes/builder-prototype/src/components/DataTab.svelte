<script>
  import {context, lookupTables} from '../lib/sample.js'
  import {evaluate, validate} from '../lib/cel.js'
  import {doc, templateData} from '../lib/state.svelte.js'

  const SOURCES = {company: 'Company settings', customer: 'Customer record', project: 'Project', report: 'Report'}
  const EXAMPLES = [
    {label: 'XOR', expr: 'xor(answers.attack_found, answers.cvss >= 9.0)'},
    {label: 'SWITCH', expr: 'switch(severity_label, {"Critical": "Call the customer now", "High": "Escalate within 4 hours"}, "Normal handling")'},
    {label: 'Regex', expr: 're_match(answers.attackers[0].ip, "^198\\\\.51\\\\.100\\\\.")'},
    {label: 'Replace', expr: 'answers.summary.replace("customer portal", "self-service portal")'},
    {label: 'Mask', expr: 're_replace(answers.attackers[0].ip, "\\\\.[0-9]+$", ".x")'},
    {label: 'Lookup', expr: 'lookup("severity_da", severity_label.lowerAscii())'},
    {label: 'Sum', expr: 'sum(answers.attackers.map(a, a.attempts))'},
    {label: 'Rejected', expr: 'answers.summary.matches("^(a+)+$")'},
  ]

  let playground = $state(EXAMPLES[1].expr)
  const data = $derived(templateData(doc.answers))
  const result = $derived(evaluate(playground, data))
  const flatContext = Object.entries(context).flatMap(([group, values]) => Object.entries(values).map(([k, v]) => ({name: `${group}.${k}`, value: v, source: SOURCES[group]})))
  const questionType = (key) => doc.questions.find((q) => q.key === key)?.type
  const show = (v) => (typeof v === 'string' ? JSON.stringify(v) : JSON.stringify(v, null, 0))

  function setComputed(i, patch) {
    doc.computed = doc.computed.map((c, j) => (j === i ? {...c, ...patch} : c))
  }
</script>

<div class="data">
  <div class="intro">
    <h2>What a template can read</h2>
    <p>Context is filled in from the customer and project, answers come from the form, and calculated values are CEL expressions. Every rule and every <span class="mono">{'{{variable}}'}</span> in the layout reads from here.</p>
  </div>

  <section class="panel" aria-labelledby="ctx-h">
    <div class="panel-head"><h2 id="ctx-h">Context</h2><span class="pill plain">Read-only</span></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th scope="col">Variable</th><th scope="col">Sample value</th><th scope="col">Filled from</th></tr></thead>
        <tbody>
          {#each flatContext as row (row.name)}
            <tr><td class="mono">{row.name}</td><td>{row.value}</td><td class="muted">{row.source}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel" aria-labelledby="ans-h">
    <div class="panel-head"><h2 id="ans-h">Answers</h2><span class="pill plain">Edit them on the Preview tab</span></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th scope="col">Variable</th><th scope="col">Sample value</th></tr></thead>
        <tbody>
          {#each Object.entries(doc.answers) as [key, value] (key)}
            <tr>
              <td class="mono">answers.{key}</td>
              <td class:mono={Array.isArray(value)} class="value">{questionType(key) === 'secret' ? '•••••••• (masked)' : Array.isArray(value) ? `${value.length} rows` : show(value)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel" aria-labelledby="calc-h">
    <div class="panel-head"><h2 id="calc-h">Calculated values</h2></div>
    <div class="panel-body">
      {#each doc.computed as c, i (c.name)}
        {@const r = evaluate(c.expr, data)}
        <div class="calc">
          <div class="calc-head"><span class="mono">{c.name}</span><span class="muted">{c.label}</span></div>
          <label class="sr" for="calc-{i}">Expression for {c.label}</label>
          <textarea id="calc-{i}" class="input mono" rows="2" value={c.expr} oninput={(e) => setComputed(i, {expr: e.currentTarget.value})}></textarea>
          {#if r.ok}<span class="pill ok">Result: {show(r.value)}</span>{:else}<span class="pill critical wrap">Error: {r.error}</span>{/if}
        </div>
      {/each}
    </div>
  </section>

  <section class="panel" aria-labelledby="try-h">
    <div class="panel-head"><h2 id="try-h">Try an expression</h2></div>
    <div class="panel-body">
      <div class="examples" role="group" aria-label="Examples">
        {#each EXAMPLES as ex (ex.label)}
          <button type="button" class="btn" class:primary={playground === ex.expr} onclick={() => (playground = ex.expr)}>{ex.label}</button>
        {/each}
      </div>
      <label class="sr" for="try">CEL expression</label>
      <textarea id="try" class="input mono" rows="3" bind:value={playground} spellcheck="false"></textarea>
      <div class="outcome" aria-live="polite">
        {#if result.ok}
          <span class="pill ok">Result</span><code class="mono">{show(result.value)}</code>
        {:else}
          <span class="pill critical">{validate(playground) ? 'Rejected' : 'Error'}</span><span class="err">{result.error}</span>
        {/if}
      </div>
      <p class="note">Regular expressions run on RE2 (re2js), the same engine family as the server, so a hostile pattern cannot hang the page. Expressions can only read data; they cannot call out or run code.</p>
    </div>
  </section>

  <section class="panel" aria-labelledby="lk-h">
    <div class="panel-head"><h2 id="lk-h">Lookup table: severity_da</h2></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th scope="col">Key</th><th scope="col">Value</th></tr></thead>
        <tbody>
          {#each Object.entries(lookupTables.severity_da) as [k, v] (k)}<tr><td class="mono">{k}</td><td>{v}</td></tr>{/each}
        </tbody>
      </table>
    </div>
  </section>
</div>

<style>
  .data { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
  .intro { grid-column: 1 / -1; display: grid; gap: 4px; }
  .intro h2 { font-size: 22px; }
  .intro p { margin: 0; color: var(--text-muted); max-width: 72ch; }
  .table-wrap { overflow-x: auto; padding: 0 16px 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-size: 12px; font-weight: 600; color: var(--text-muted); padding: 6px 10px; border-bottom: 1px solid var(--border-strong); }
  td { padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
  td.value { max-width: 34ch; overflow-wrap: anywhere; }
  .muted { color: var(--text-muted); }
  .calc { display: grid; gap: 6px; justify-items: start; }
  .calc textarea { min-height: 0; }
  .calc-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }
  .examples { display: flex; flex-wrap: wrap; gap: 6px; }
  .outcome { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; min-height: 28px; }
  .outcome code { overflow-wrap: anywhere; }
  .err { font-size: 13px; color: var(--critical-text); }
  .note { margin: 0; color: var(--text-muted); font-size: 12.5px; max-width: 68ch; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  textarea.mono { font-size: 12.5px; }
  @media (max-width: 960px) { .data { grid-template-columns: minmax(0, 1fr); } }
</style>
