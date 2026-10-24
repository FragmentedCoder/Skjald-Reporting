<script>
  import {dndzone} from 'svelte-dnd-action'
  import Palette from './Palette.svelte'
  import ConditionEditor from './ConditionEditor.svelte'
  import {FIELD_TYPES, newQuestion} from '../lib/sample.js'
  import {describeRule} from '../lib/cel.js'
  import {doc, updateQuestion, removeQuestion, renameKey} from '../lib/state.svelte.js'

  const HINTS = {
    text: 'One line', longtext: 'Paragraphs', number: 'Scores, counts', yesno: 'A single choice',
    dropdown: 'Pick from a list', datetime: 'When it happened', ip: 'IPv4 or IPv6', repeating: 'A table of rows', secret: 'Masked in the PDF',
  }
  const COLUMN_TYPES = ['text', 'number', 'ip', 'datetime']
  const paletteEntries = Object.entries(FIELD_TYPES).map(([kind, t]) => ({id: `pal-${kind}`, kind, label: t.label, hint: HINTS[kind], glyph: t.icon}))

  const selected = $derived(doc.questions.find((q) => q.id === doc.selectedQuestion))
  let keyDraft = $state('')
  let keyError = $state('')
  $effect(() => {
    keyDraft = selected?.key ?? ''
    keyError = ''
  })

  const usedBy = $derived(selected ? doc.blocks.filter((b) => b.question === selected.key || b.showWhen?.field === selected.key || (b.text ?? '').includes(`answers.${selected.key}`)).length : 0)

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
</script>

<div class="workspace">
  <Palette entries={paletteEntries} type="questions" title="Field types" onadd={addAfterSelected} />

  <section class="canvas" aria-label="Questions">
    <div class="intro">
      <h2>Questions the technician answers</h2>
      <p>This is the form shown when a report is filled in. Each answer becomes a variable the layout and rules can use.</p>
    </div>
    <ol
      class="cards"
      use:dndzone={{items: doc.questions, type: 'questions', flipDurationMs: 150, dropTargetStyle: {outline: '2px dashed var(--link)', outlineOffset: '4px'}}}
      onconsider={consider}
      onfinalize={finalize}
    >
      {#each doc.questions as q, i (q.id)}
        <li class="card" class:selected={q.id === doc.selectedQuestion}>
          <button type="button" class="pick" onclick={() => (doc.selectedQuestion = q.id)} aria-label="Edit {q.label}"><span class="hit"></span></button>
          <span class="glyph" aria-hidden="true">{FIELD_TYPES[q.type]?.icon}</span>
          <span class="body">
            <span class="label">{i + 1}. {q.label}</span>
            <span class="meta"><span class="mono">answers.{q.key}</span> · {FIELD_TYPES[q.type]?.label}</span>
            {#if q.type === 'repeating'}<span class="meta">Columns: {q.columns.map((c) => c.label).join(', ')}</span>{/if}
          </span>
          <span class="chips">
            {#if q.required}<span class="pill plain">Required</span>{/if}
            {#if q.type === 'secret'}<span class="pill info">Masked</span>{/if}
            {#if q.showWhen}<span class="pill warning wrap">Only when: {describeRule(q.showWhen, doc.questions)}</span>{/if}
          </span>
        </li>
      {/each}
    </ol>
  </section>

  <aside class="panel props" aria-label="Question properties">
    {#if selected}
      <div class="panel-head">
        <h2>{FIELD_TYPES[selected.type].label}</h2>
        <button type="button" class="btn quiet" onclick={() => removeQuestion(selected.id)}>Remove</button>
      </div>
      <div class="panel-body">
        <div class="field"><label for="q-label">Question</label>
          <input id="q-label" class="input" value={selected.label} oninput={(e) => updateQuestion(selected.id, {label: e.currentTarget.value})} /></div>
        <div class="field"><label for="q-key">Variable name</label>
          <div class="key-row">
            <span class="mono prefix">answers.</span>
            <input id="q-key" class="input mono" bind:value={keyDraft} onchange={commitKey} aria-invalid={!!keyError} aria-describedby="q-key-hint" />
          </div>
          {#if keyError}<span class="error" role="alert">{keyError}</span>
          {:else}<span class="hint" id="q-key-hint">Used in text and rules.{usedBy ? ` Renaming updates the ${usedBy} block${usedBy === 1 ? '' : 's'} that use it.` : ''}</span>{/if}
        </div>
        <div class="field"><label for="q-help">Help text</label>
          <input id="q-help" class="input" value={selected.help} oninput={(e) => updateQuestion(selected.id, {help: e.currentTarget.value})} /></div>
        <label class="check"><input type="checkbox" checked={selected.required} onchange={(e) => updateQuestion(selected.id, {required: e.currentTarget.checked})} /> Required before the report can be signed</label>

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
                  onclick={() => updateQuestion(selected.id, {columns: selected.columns.filter((_, j) => j !== i)})}>Remove</button>
              </div>
            {/each}
            <button type="button" class="btn" onclick={() => updateQuestion(selected.id, {columns: [...selected.columns, {key: `col_${selected.columns.length + 1}`, label: 'New column', type: 'text'}]})}>Add column</button>
          </fieldset>
        {:else if selected.type === 'secret'}
          <p class="note">Secret answers are always masked in the PDF and in the preview.</p>
        {/if}

        <ConditionEditor idPrefix="question" rule={selected.showWhen} onchange={(rule) => updateQuestion(selected.id, {showWhen: rule})} />
      </div>
    {:else}
      <div class="panel-body"><p class="note">Select a question to edit it.</p></div>
    {/if}
  </aside>
</div>

<style>
  .workspace { display: grid; grid-template-columns: 236px minmax(0, 1fr) 320px; gap: 16px; align-items: start; }
  .canvas { min-width: 0; display: grid; gap: 14px; }
  .intro { display: grid; gap: 4px; }
  .intro h2 { font-size: 22px; }
  .intro p { margin: 0; color: var(--text-muted); max-width: 68ch; }
  .cards { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; min-height: 120px; }
  .card { position: relative; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px; align-items: center;
    padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); }
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
  .meta { font-size: 12.5px; color: var(--text-muted); overflow-wrap: anywhere; }
  .meta .mono { font-size: 12px; }
  .chips { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; max-width: 240px; }
  .props { position: sticky; top: 12px; }
  .key-row { display: flex; align-items: center; gap: 6px; }
  .prefix { color: var(--text-muted); }
  .error { font-size: 12px; color: var(--critical-text); }
  .columns { display: grid; gap: 8px; margin: 0; padding: 10px 12px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); }
  legend { padding: 0 4px; font-size: 12.5px; font-weight: 600; }
  .column { display: grid; grid-template-columns: minmax(0, 1fr) 110px auto; gap: 6px; }
  .columns > .btn { justify-self: start; }
  .note { margin: 0; color: var(--text-muted); font-size: 13px; }
  @media (max-width: 1180px) { .workspace { grid-template-columns: 220px minmax(0, 1fr); } .props { grid-column: 1 / -1; position: static; } }
  @media (max-width: 860px) {
    .workspace { grid-template-columns: minmax(0, 1fr); }
    .card { grid-template-columns: auto minmax(0, 1fr); }
    .chips { grid-column: 1 / -1; justify-content: flex-start; max-width: none; }
  }
</style>
