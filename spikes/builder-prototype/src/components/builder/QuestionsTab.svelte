<script>
  import {dndzone} from 'svelte-dnd-action'
  import Palette from '../Palette.svelte'
  import ConditionEditor from '../ConditionEditor.svelte'
  import Where from '../Where.svelte'
  import {FIELD_TYPES, BLOCK_TYPES, newQuestion} from '../../lib/sample.js'
  import {describeRule} from '../../lib/cel.js'
  import {maskSecret} from '../../lib/pages.js'
  import {doc, updateQuestion, removeQuestion, renameKey, usage} from '../../lib/state.svelte.js'

  const COLUMN_TYPES = ['text', 'number', 'ip', 'datetime']
  const paletteEntries = Object.entries(FIELD_TYPES).map(([kind, t]) => ({id: `pal-${kind}`, kind, label: t.label, hint: t.hint, glyph: t.icon}))

  const selected = $derived(doc.questions.find((q) => q.id === doc.selectedQuestion))
  let keyDraft = $state('')
  let keyError = $state('')
  $effect(() => {
    keyDraft = selected?.key ?? ''
    keyError = ''
  })

  // Step numbers for the cards: questions before the first step belong to step 1.
  const stepOf = $derived.by(() => {
    const map = {}
    let n = doc.questions[0]?.type === 'group' ? 0 : 1
    for (const q of doc.questions) {
      if (q.type === 'group') n += 1
      map[q.id] = n
    }
    return map
  })
  const usedIn = (q) => (q.type === 'group' ? [] : usage(q.key))
  const blockName = (b) => (b.kind === 'cover' ? 'the cover page' : b.kind === 'section' ? `section “${b.title}”` : `${BLOCK_TYPES[b.kind]?.label.toLowerCase()} block`)

  function consider(e) {
    doc.questions = e.detail.items
  }
  function finalize(e) {
    let fresh = null
    doc.questions = e.detail.items.map((item) => (item.palette ? (fresh = newQuestion(item.kind)) : item))
    if (fresh) doc.selectedQuestion = fresh.id
  }
  function addAfterSelected(kind) {
    const q = newQuestion(kind)
    const index = doc.questions.findIndex((x) => x.id === doc.selectedQuestion)
    const next = [...doc.questions]
    next.splice(index + 1, 0, q)
    doc.questions = next
    doc.selectedQuestion = q.id
  }
  function commitKey() {
    keyError = renameKey(selected.id, keyDraft.trim()) ?? ''
  }
  function setColumn(i, patch) {
    updateQuestion(selected.id, {columns: selected.columns.map((c, j) => (j === i ? {...c, ...patch} : c))})
  }
  const setSecret = (patch) => updateQuestion(selected.id, {secret: {...(selected.secret ?? {pdf: 'partial', ends: 2}), ...patch}})
</script>

<div class="workspace">
  <Palette entries={paletteEntries} type="questions" title="Field types" onadd={addAfterSelected} />

  <section class="canvas" aria-label="Form questions">
    <div class="intro">
      <div class="intro-title"><h2>The form</h2><Where form /></div>
      <p>What the technician sees and fills in, step by step. Each answer gets a variable name, like <span class="mono">answers.cvss</span>, which the PDF and the rules can use. Nothing here is printed unless a block on the Layout tab uses it.</p>
    </div>
    <ol
      class="cards"
      use:dndzone={{items: doc.questions, type: 'questions', flipDurationMs: 150, dropTargetStyle: {outline: '2px dashed var(--link)', outlineOffset: '4px'}}}
      onconsider={consider}
      onfinalize={finalize}
    >
      {#each doc.questions as q (q.id)}
        {@const uses = usedIn(q)}
        <li class="card" class:group={q.type === 'group'} class:selected={q.id === doc.selectedQuestion}>
          <button type="button" class="pick" onclick={() => (doc.selectedQuestion = q.id)} aria-label="Edit {q.label}"><span class="hit"></span></button>
          {#if q.type === 'group'}
            <span class="body">
              <span class="overline">Step {stepOf[q.id]}</span>
              <span class="step-title">{q.label}</span>
              {#if q.help}<span class="meta">{q.help}</span>{/if}
            </span>
          {:else}
            <span class="glyph" aria-hidden="true">{FIELD_TYPES[q.type]?.icon}</span>
            <span class="body">
              <span class="label">{q.label}{q.required ? ' *' : ''}</span>
              <span class="meta"><span class="mono">answers.{q.key}</span> · {FIELD_TYPES[q.type]?.label}</span>
              {#if q.type === 'repeating'}<span class="meta">Columns: {q.columns.map((c) => c.label).join(', ')}</span>{/if}
              <span class="uses">{#if uses.length}In the PDF via {uses.map(blockName).join(', ')}{:else}Not used in the PDF{/if}</span>
            </span>
            <span class="chips">
              <Where form pdf={uses.length > 0} compact />
              {#if q.type === 'secret'}<span class="pill info">PDF shows {maskSecret('Hunter2-portal-admin', q.secret)}</span>{/if}
              {#if q.showWhen}<span class="pill warning wrap">Only when {describeRule(q.showWhen, doc.questions)}</span>{/if}
            </span>
          {/if}
        </li>
      {/each}
    </ol>
  </section>

  <aside class="panel props" aria-label="Question settings">
    {#if selected}
      <div class="panel-head">
        <h2>{FIELD_TYPES[selected.type].label}</h2>
        <button type="button" class="btn quiet" onclick={() => removeQuestion(selected.id)}>Remove</button>
      </div>
      <div class="panel-body">
        {#if selected.type === 'group'}
          <div class="group-head"><h3>In the form</h3><Where form compact /></div>
          <div class="field"><label for="q-label">Step title</label>
            <input id="q-label" class="input" value={selected.label} oninput={(e) => updateQuestion(selected.id, {label: e.currentTarget.value})} /></div>
          <div class="field"><label for="q-help">Description for the technician</label>
            <textarea id="q-help" class="input" rows="3" value={selected.help} oninput={(e) => updateQuestion(selected.id, {help: e.currentTarget.value})}></textarea>
            <span class="hint">Shown at the top of the step. Not printed.</span></div>
        {:else}
          <div class="group-head"><h3>In the form</h3><Where form compact /></div>
          <div class="field"><label for="q-label">Question</label>
            <input id="q-label" class="input" value={selected.label} oninput={(e) => updateQuestion(selected.id, {label: e.currentTarget.value})} /></div>
          <div class="field"><label for="q-help">Help text</label>
            <input id="q-help" class="input" value={selected.help} oninput={(e) => updateQuestion(selected.id, {help: e.currentTarget.value})} />
            <span class="hint">Shown under the field. Not printed.</span></div>
          <label class="check"><input type="checkbox" checked={selected.required} onchange={(e) => updateQuestion(selected.id, {required: e.currentTarget.checked})} /> Required before the report can be sent for review</label>

          {#if selected.type === 'dropdown'}
            <div class="field"><label for="q-options">Options, one per line</label>
              <textarea id="q-options" class="input" value={selected.options.join('\n')}
                oninput={(e) => updateQuestion(selected.id, {options: e.currentTarget.value.split('\n').map((s) => s.trim()).filter(Boolean)})}></textarea></div>
          {:else if selected.type === 'repeating'}
            <fieldset class="columns">
              <legend>Columns</legend>
              {#each selected.columns as c, i (i)}
                <div class="column">
                  <input class="input" aria-label="Column {i + 1} label" value={c.label} oninput={(e) => setColumn(i, {label: e.currentTarget.value})} />
                  <select class="input" aria-label="Column {i + 1} type" value={c.type} onchange={(e) => setColumn(i, {type: e.currentTarget.value})}>
                    {#each COLUMN_TYPES as t (t)}<option value={t}>{FIELD_TYPES[t].label}</option>{/each}
                  </select>
                  <button type="button" class="btn quiet" aria-label="Remove column {c.label}" disabled={selected.columns.length === 1}
                    onclick={() => updateQuestion(selected.id, {columns: selected.columns.filter((_, j) => j !== i)})}>×</button>
                </div>
              {/each}
              <button type="button" class="btn" onclick={() => updateQuestion(selected.id, {columns: [...selected.columns, {key: `col_${selected.columns.length + 1}`, label: 'New column', type: 'text'}]})}>Add column</button>
            </fieldset>
          {/if}

          {#if selected.type === 'secret'}
            <div class="group-head"><h3>In the PDF</h3><Where pdf compact /></div>
            <div class="field"><label for="q-secret-pdf">How the secret is printed</label>
              <select id="q-secret-pdf" class="input" value={selected.secret?.pdf ?? 'partial'} onchange={(e) => setSecret({pdf: e.currentTarget.value})}>
                <option value="partial">Partly: first and last characters</option>
                <option value="omit">Not printed</option>
              </select></div>
            {#if (selected.secret?.pdf ?? 'partial') === 'partial'}
              <div class="field"><label for="q-secret-ends">Characters shown at each end</label>
                <select id="q-secret-ends" class="input" value={String(selected.secret?.ends ?? 2)} onchange={(e) => setSecret({ends: Number(e.currentTarget.value)})}>
                  <option value="1">1</option><option value="2">2</option><option value="3">3</option>
                </select>
                <span class="hint">Never more than a quarter of the secret, so short ones show less. The dots don't reveal its length.</span></div>
            {/if}
            <div class="example">
              <span class="overline">Example</span>
              <span><span class="mono">Hunter2-portal-admin</span> → <span class="mono">{maskSecret('Hunter2-portal-admin', selected.secret)}</span></span>
              <span><span class="mono">Summer26</span> → <span class="mono">{maskSecret('Summer26', selected.secret)}</span></span>
            </div>
            <p class="note">Technicians see the full value in the report after confirming with MFA, for 30 seconds at a time. Every reveal is logged. The customer gets the full value from the technician, by phone or a secure link.</p>
          {/if}

          <div class="group-head"><h3>Variable</h3><Where builder compact /></div>
          <div class="field"><label for="q-key">Name used in text and rules</label>
            <div class="key-row">
              <span class="mono prefix">answers.</span>
              <input id="q-key" class="input mono" bind:value={keyDraft} onchange={commitKey} aria-invalid={!!keyError} aria-describedby="q-key-hint" />
            </div>
            {#if keyError}<span class="error" role="alert">{keyError}</span>
            {:else}<span class="hint" id="q-key-hint">Renaming updates every block, rule and calculated value that uses it.</span>{/if}
          </div>
        {/if}

        <div class="group-head"><h3>When it appears</h3></div>
        <ConditionEditor idPrefix="question" self={selected.key} rule={selected.showWhen} onchange={(rule) => updateQuestion(selected.id, {showWhen: rule})} />
      </div>
    {:else}
      <div class="panel-body"><p class="note">Select a question to edit it.</p></div>
    {/if}
  </aside>
</div>

<style>
  .workspace { display: grid; grid-template-columns: 236px minmax(0, 1fr) 330px; gap: 16px; align-items: start; }
  .canvas { min-width: 0; display: grid; gap: 14px; }
  .intro { display: grid; gap: 4px; }
  .intro-title { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; }
  .intro h2 { font-size: 22px; }
  .intro p { margin: 0; color: var(--text-muted); max-width: 72ch; }
  .cards { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; min-height: 120px; }
  .card { position: relative; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px; align-items: center;
    padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); margin-left: 18px; }
  .card.group { grid-template-columns: minmax(0, 1fr); margin: 10px 0 0; background: var(--surface-subtle); }
  .card.selected { border-color: var(--link); box-shadow: 0 0 0 1px var(--link); }
  .pick { position: absolute; inset: 0; border: 0; background: transparent; border-radius: inherit; cursor: pointer; }
  .pick:focus-visible { outline-offset: -2px; }
  /* svelte-dnd-action won't start a drag when the pressed element has a value (as buttons do), so a span inside takes the press. */
  .hit { position: absolute; inset: 0; border-radius: inherit; }
  .card > :not(.pick) { position: relative; pointer-events: none; }
  .glyph { width: 34px; height: 34px; display: grid; place-items: center; border-radius: var(--radius-sm); background: var(--surface-subtle);
    font-family: var(--font-mono); font-size: 12px; font-weight: 500; }
  .body { display: grid; gap: 2px; min-width: 0; }
  .label { font-weight: 600; }
  .step-title { font-family: var(--font-display); font-size: 19px; }
  .meta, .uses { font-size: 12.5px; color: var(--text-muted); overflow-wrap: anywhere; }
  .meta .mono { font-size: 12px; }
  .chips { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; max-width: 250px; }
  .props { position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto; }
  .group-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-top: 10px; border-top: 1px solid var(--border); }
  .group-head:first-child { padding-top: 0; border-top: 0; }
  .group-head h3 { margin: 0; font-family: var(--font-sans); font-size: 12px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); }
  .key-row { display: flex; align-items: center; gap: 6px; }
  .prefix { color: var(--text-muted); }
  .error { font-size: 12px; color: var(--critical-text); }
  .columns { display: grid; gap: 8px; margin: 0; padding: 10px 12px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); min-width: 0; }
  legend { padding: 0 4px; font-size: 12.5px; font-weight: 600; }
  .column { display: grid; grid-template-columns: minmax(0, 1fr) 110px auto; gap: 6px; }
  .columns > .btn { justify-self: start; }
  .example { display: grid; gap: 2px; padding: 8px 10px; border-radius: var(--radius-md); background: var(--surface-subtle); font-size: 12.5px; }
  .note { margin: 0; color: var(--text-muted); font-size: 12.5px; }
  @media (max-width: 1180px) { .workspace { grid-template-columns: 220px minmax(0, 1fr); } .props { grid-column: 1 / -1; position: static; max-height: none; } }
  @media (max-width: 860px) {
    .workspace { grid-template-columns: minmax(0, 1fr); }
    .card { grid-template-columns: auto minmax(0, 1fr); margin-left: 8px; }
    .chips { grid-column: 1 / -1; justify-content: flex-start; max-width: none; }
  }
</style>
