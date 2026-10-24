<script>
  // What a template can read, with what each value is, where it comes from, and how to use it.
  import Where from '../Where.svelte'
  import {context, contextInfo, FIELD_TYPES} from '../../lib/sample.js'
  import {evaluate, validate} from '../../lib/cel.js'
  import {interpolate, maskSecret, formatValue} from '../../lib/pages.js'
  import {doc, library, session, templateData, usage, KEY_PATTERN} from '../../lib/state.svelte.js'

  const ABOUT = {
    'company.name': "Your company's name", 'company.cvr': "Your company's CVR number",
    'customer.name': "The customer's name", 'customer.cvr': "The customer's CVR number", 'customer.address': "The customer's address",
    'customer.contact': "The customer's main contact person",
    'project.name': "The project's name", 'project.number': "The project's number",
    'report.number': 'The report number, with the template prefix', 'report.classification': 'The classification label, like TLP:AMBER',
    'report.technician': 'The technician who writes the report', 'report.reviewer': 'The reviewer who approves it',
  }

  const FUNCTIONS = [
    {name: 'a ? b : c', about: 'If a is true, b; otherwise c. Chain them for IF / ELSE IF / ELSE.', example: 'answers.cvss >= 9.0 ? "Call now" : answers.cvss >= 7.0 ? "Within 4 hours" : "Next working day"'},
    {name: '&&   ||   !', about: 'AND, OR and NOT.', example: 'answers.attack_found && !(answers.cvss < 7.0)'},
    {name: 'xor(a, b)', about: 'True when exactly one of a and b is true.', example: 'xor(answers.attack_found, answers.cvss >= 9.0)'},
    {name: 'switch(value, cases, default)', about: 'Picks the case that matches value, or the default.', example: 'switch(severity_label, {"Critical": "Call the customer now", "High": "Escalate within 4 hours"}, "Normal handling")'},
    {name: 're_match(text, pattern)', about: 'True when the regular expression matches. Uses RE2, so no pattern can hang the server.', example: 're_match(answers.attackers[0].ip, "^198\\\\.51\\\\.100\\\\.")'},
    {name: 're_replace(text, pattern, with)', about: 'Replaces every match of a regular expression.', example: 're_replace(answers.attackers[0].ip, "\\\\.[0-9]+$", ".x")'},
    {name: 'text.replace(old, new)', about: 'Replaces every copy of some text.', example: 'answers.summary.replace("customer portal", "self-service portal")'},
    {name: 'list.size()', about: 'How many rows or characters.', example: 'answers.attackers.size()'},
    {name: 'list.filter(x, rule)', about: 'The rows where the rule is true.', example: 'answers.attackers.filter(a, a.attempts > 100).size()'},
    {name: 'list.exists(x, rule)', about: 'True when at least one row matches.', example: 'answers.attackers.exists(a, a.status == "Monitoring")'},
    {name: 'list.map(x, value)', about: 'One value per row.', example: 'answers.attackers.map(a, a.ip)'},
    {name: 'sum(list)', about: 'Adds up numbers.', example: 'sum(answers.attackers.map(a, a.attempts))'},
    {name: 'lookup(table, key)', about: 'Reads a value from a data table in the library.', example: 'lookup("severity_da", severity_label.lowerAscii())'},
    {name: 'text.lowerAscii()', about: 'The text in lower case.', example: 'severity_label.lowerAscii()'},
  ]

  let playground = $state(FUNCTIONS[3].example)
  let tryBox = $state()
  const data = $derived(templateData(doc.answers))
  const result = $derived(evaluate(playground, data))
  const show = (v) => (typeof v === 'string' ? JSON.stringify(v) : JSON.stringify(v))
  const printed = (text) => interpolate(text, data, doc.questions).map((p) => p.text).join('')
  const contextRows = Object.entries(context).flatMap(([group, values]) => Object.entries(values).map(([k, v]) => ({name: `${group}.${k}`, value: v, source: contextInfo[group].source})))

  function tryIt(expr) {
    playground = expr
    tryBox?.scrollIntoView({behavior: 'smooth', block: 'center'})
  }
  function goTo(id) {
    document.getElementById(id)?.scrollIntoView({behavior: 'smooth', block: 'start'})
  }
  function setComputed(i, patch) {
    doc.computed = doc.computed.map((c, j) => (j === i ? {...c, ...patch} : c))
  }
  function addComputed() {
    let n = doc.computed.length + 1
    while (doc.computed.some((c) => c.name === `value_${n}`)) n += 1
    doc.computed = [...doc.computed, {name: `value_${n}`, label: 'New calculated value', about: '', expr: '"Hello, " + customer.name'}]
  }
  const nameProblem = (c, i) => !KEY_PATTERN.test(c.name) ? 'Use lower-case letters, digits and underscores.' : doc.computed.some((x, j) => j !== i && x.name === c.name) ? 'Another value already has this name.' : ''
  const answerSample = (q) => {
    const v = doc.answers[q.key]
    if (q.type === 'secret') return `${maskSecret(v, q.secret)} (partly shown)`
    if (q.type === 'photo') return v ? 'An image' : '—'
    if (q.type === 'repeating') return formatValue(Array.isArray(v) ? v : [], q.type)
    return formatValue(v, q.type)
  }
</script>

<div class="data">
  <div class="intro">
    <div class="intro-title"><h2>What a template can read</h2><Where builder /></div>
    <p>Every value below has a name. Put the name in double braces in a text block and it is printed in the PDF. Rules and calculated values use the same names without braces.</p>
    <div class="example big">
      <div><span class="overline">You write</span><code class="mono">Prepared for {'{{customer.name}}'} by {'{{report.technician}}'}. Severity: {'{{severity_label}}'}.</code></div>
      <div><span class="overline">The PDF says</span><span>{printed('Prepared for {{customer.name}} by {{report.technician}}. Severity: {{severity_label}}.')}</span></div>
    </div>
    <nav class="jump" aria-label="On this tab">
      {#each [['d-context', 'Report details'], ['d-answers', 'Answers'], ['d-library', 'Library'], ['d-calc', 'Calculated values'], ['d-tables', 'Data tables'], ['d-functions', 'Functions'], ['d-try', 'Try an expression']] as [id, label] (id)}
        <button type="button" class="btn quiet" onclick={() => goTo(id)}>{label}</button>
      {/each}
    </nav>
  </div>

  <section class="panel" id="d-context" aria-labelledby="ctx-h">
    <div class="panel-head"><h2 id="ctx-h">Report details</h2><span class="pill plain">Filled in automatically</span></div>
    <p class="lead">Skjald fills these in from the company, customer, project and report when a report is started. Nobody types them.</p>
    <div class="example"><span class="overline">Example</span><code class="mono">{'{{customer.contact}}'}, {'{{customer.name}}'}</code><span>→ {printed('{{customer.contact}}, {{customer.name}}')}</span></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th scope="col">Name</th><th scope="col">What it is</th><th scope="col">Sample</th><th scope="col">Comes from</th></tr></thead>
        <tbody>
          {#each contextRows as row (row.name)}
            <tr><td class="mono">{row.name}</td><td>{ABOUT[row.name] ?? ''}</td><td>{row.value}</td><td class="muted">{row.source}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel" id="d-answers" aria-labelledby="ans-h">
    <div class="panel-head"><h2 id="ans-h">Answers</h2><Where form compact /></div>
    <p class="lead">One per question on the Questions tab, filled in by the technician. Secrets are printed only partly.</p>
    <div class="example"><span class="overline">Examples</span>
      <span>In text: <code class="mono">CVSS {'{{answers.cvss}}'}</code> → {printed('CVSS {{answers.cvss}}')}</span>
      <span>In a rule: <code class="mono">answers.attack_found == true</code></span>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th scope="col">Name</th><th scope="col">Question</th><th scope="col">Type</th><th scope="col">Sample</th><th scope="col">In the PDF</th></tr></thead>
        <tbody>
          {#each doc.questions.filter((q) => q.type !== 'group') as q (q.id)}
            <tr>
              <td class="mono">answers.{q.key}</td><td>{q.label}</td><td class="muted">{FIELD_TYPES[q.type]?.label}</td>
              <td class="value">{answerSample(q)}</td><td>{usage(q.key).length ? 'Yes' : 'Not used'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel" id="d-library" aria-labelledby="lib-h">
    <div class="panel-head"><h2 id="lib-h">Library</h2><button type="button" class="btn" onclick={() => (session.view = 'library')}>Open the library</button></div>
    <p class="lead">Shared by every template and report, and kept up to date by your team. Change a value once and every new report uses it; signed reports keep the value they were signed with.</p>
    <div class="example"><span class="overline">Examples</span>
      <span>A variable: <code class="mono">Call {'{{vars.support_phone}}'}</code> → {printed('Call {{vars.support_phone}}')}</span>
      <span>A text snippet: <code class="mono">{'{{text.nis2_deadlines}}'}</code> → {printed('{{text.nis2_deadlines}}')}</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th scope="col">Name</th><th scope="col">What it is</th><th scope="col">Value</th></tr></thead>
        <tbody>
          {#each library.vars as v (v.key)}<tr><td class="mono">vars.{v.key}</td><td>{v.about}</td><td class="value">{v.value}</td></tr>{/each}
          {#each library.text as t (t.key)}<tr><td class="mono">text.{t.key}</td><td>{t.about}</td><td class="value">{t.value}</td></tr>{/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel" id="d-calc" aria-labelledby="calc-h">
    <div class="panel-head"><h2 id="calc-h">Calculated values</h2><button type="button" class="btn" onclick={addComputed}>Add a calculated value</button></div>
    <p class="lead">Worked out from other values with a short expression, every time an answer changes. Use them like any other name, in text and in rules.</p>
    <div class="panel-body">
      {#each doc.computed as c, i (i)}
        {@const r = evaluate(c.expr, data)}
        {@const problem = nameProblem(c, i)}
        <div class="calc">
          <div class="calc-grid">
            <div class="field"><label for="calc-name-{i}">Name</label>
              <input id="calc-name-{i}" class="input mono" value={c.name} oninput={(e) => setComputed(i, {name: e.currentTarget.value.trim()})} aria-invalid={!!problem} />
              {#if problem}<span class="error">{problem}</span>{/if}</div>
            <div class="field"><label for="calc-about-{i}">What it is</label>
              <input id="calc-about-{i}" class="input" value={c.about} oninput={(e) => setComputed(i, {about: e.currentTarget.value})} /></div>
          </div>
          <div class="field"><label for="calc-{i}">Expression</label>
            <textarea id="calc-{i}" class="input mono" rows="2" value={c.expr} oninput={(e) => setComputed(i, {expr: e.currentTarget.value})}></textarea></div>
          <div class="outcome">
            {#if r.ok}<span class="pill ok">Result</span><code class="mono">{show(r.value)}</code><span class="muted">Use it as <span class="mono">{`{{${c.name}}}`}</span></span>
            {:else}<span class="pill critical">Error</span><span class="err">{r.error}</span>{/if}
          </div>
        </div>
      {/each}
    </div>
  </section>

  <section class="panel" id="d-tables" aria-labelledby="lk-h">
    <div class="panel-head"><h2 id="lk-h">Data tables</h2><button type="button" class="btn" onclick={() => (session.view = 'library')}>Edit in the library</button></div>
    <p class="lead">Lists of keys and values in the library, read with <span class="mono">lookup(table, key)</span>. Good for translations, standards and anything that maps one value to another.</p>
    <div class="example"><span class="overline">Example</span><code class="mono">lookup("media_destruction", "ssd")</code><span>→ {show(evaluate('lookup("media_destruction", "ssd")', data).value)}</span></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th scope="col">Table</th><th scope="col">What it is</th><th scope="col">Keys</th></tr></thead>
        <tbody>{#each library.tables as t (t.key)}<tr><td class="mono">{t.key}</td><td>{t.about}</td><td class="mono value">{t.rows.map((r) => r.key).join(', ')}</td></tr>{/each}</tbody>
      </table>
    </div>
  </section>

  <section class="panel wide" id="d-functions" aria-labelledby="fn-h">
    <div class="panel-head"><h2 id="fn-h">Functions</h2></div>
    <p class="lead">What you can use in rules and calculated values. Expressions only read data; they can't change anything, reach the network or run code. Results below use the sample answers.</p>
    <div class="table-wrap">
      <table class="fn">
        <thead><tr><th scope="col">Function</th><th scope="col">What it does</th><th scope="col">Example and result</th><th scope="col"><span class="sr">Try it</span></th></tr></thead>
        <tbody>
          {#each FUNCTIONS as f (f.name)}
            {@const r = evaluate(f.example, data)}
            <tr>
              <td class="mono nowrap">{f.name}</td>
              <td>{f.about}</td>
              <td><code class="mono">{f.example}</code><span class="res">→ {r.ok ? show(r.value) : r.error}</span></td>
              <td><button type="button" class="btn quiet" onclick={() => tryIt(f.example)}>Try</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  <section class="panel wide" id="d-try" aria-labelledby="try-h" bind:this={tryBox}>
    <div class="panel-head"><h2 id="try-h">Try an expression</h2></div>
    <div class="panel-body">
      <label class="sr" for="try">Expression</label>
      <textarea id="try" class="input mono" rows="3" bind:value={playground} spellcheck="false"></textarea>
      <div class="outcome" aria-live="polite">
        {#if result.ok}
          <span class="pill ok">Result</span><code class="mono">{show(result.value)}</code>
        {:else}
          <span class="pill critical">{validate(playground) ? 'Not allowed' : 'Error'}</span><span class="err">{result.error}</span>
        {/if}
      </div>
      <p class="note">The built-in <span class="mono">matches()</span> is refused because its regular expressions can hang the browser; use <span class="mono">re_match()</span>. Expressions are limited to 2,000 characters.</p>
    </div>
  </section>
</div>

<style>
  .data { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
  .intro { grid-column: 1 / -1; display: grid; gap: 8px; }
  .intro-title { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; }
  .intro h2 { font-size: 22px; }
  .intro p { margin: 0; color: var(--text-muted); max-width: 76ch; }
  .jump { display: flex; flex-wrap: wrap; gap: 2px; }
  .wide { grid-column: 1 / -1; }
  .lead { margin: 0; padding: 0 16px 10px; color: var(--text-muted); font-size: 13px; max-width: 76ch; }
  .example { display: grid; gap: 4px; margin: 0 16px 12px; padding: 10px 12px; border-radius: var(--radius-md); background: var(--surface-subtle); font-size: 13px; }
  .example.big { margin: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .example.big > div { display: grid; gap: 2px; min-width: 0; }
  .example code { overflow-wrap: anywhere; }
  .table-wrap { overflow-x: auto; padding: 0 16px 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-size: 12px; font-weight: 600; color: var(--text-muted); padding: 6px 10px; border-bottom: 1px solid var(--border-strong); }
  td { padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
  td.value { max-width: 34ch; overflow-wrap: anywhere; }
  .fn code { display: block; overflow-wrap: anywhere; font-size: 12px; }
  .res { display: block; font-size: 12.5px; color: var(--ok-text); overflow-wrap: anywhere; }
  .nowrap { white-space: nowrap; }
  .muted { color: var(--text-muted); }
  .calc { display: grid; gap: 6px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
  .calc:last-child { border-bottom: 0; padding-bottom: 0; }
  .calc-grid { display: grid; grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr); gap: 8px; }
  .calc textarea { min-height: 0; }
  .outcome { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; min-height: 28px; font-size: 13px; }
  .outcome code { overflow-wrap: anywhere; }
  .err, .error { font-size: 12.5px; color: var(--critical-text); }
  .note { margin: 0; color: var(--text-muted); font-size: 12.5px; max-width: 72ch; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  textarea.mono { font-size: 12.5px; }
  @media (max-width: 1100px) { .data { grid-template-columns: minmax(0, 1fr); } .example.big { grid-template-columns: minmax(0, 1fr); } }
  @media (max-width: 600px) { .calc-grid { grid-template-columns: minmax(0, 1fr); } .nowrap { white-space: normal; } }
</style>
