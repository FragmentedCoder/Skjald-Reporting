<script>
  // The form as the technician sees it. Questions with a rule appear only when the rule is true.
  import {FIELD_TYPES} from '../lib/sample.js'
  import {doc, templateData, ruleResult} from '../lib/state.svelte.js'

  const data = $derived(templateData(doc.answers))
  const visible = $derived(doc.questions.filter((q) => ruleResult(q.showWhen, data).value !== false))
  const hiddenCount = $derived(doc.questions.length - visible.length)

  const WIDTHS = {ip: 'minmax(0, 1.9fr)', number: 'minmax(0, 1fr)', text: 'minmax(0, 1.2fr)', datetime: 'minmax(0, 1.4fr)'}
  const set = (key, value) => (doc.answers[key] = value)
  const rows = (key) => (Array.isArray(doc.answers[key]) ? doc.answers[key] : [])
  function setCell(q, i, col, value) {
    doc.answers[q.key] = rows(q.key).map((r, j) => (j === i ? {...r, [col.key]: col.type === 'number' && value.trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : value} : r))
  }
  function addRow(q) {
    doc.answers[q.key] = [...rows(q.key), Object.fromEntries(q.columns.map((c) => [c.key, c.type === 'number' ? 0 : '']))]
  }
  function removeRow(q, i) {
    doc.answers[q.key] = rows(q.key).filter((_, j) => j !== i)
  }
</script>

<form class="panel answers" aria-label="Sample answers" onsubmit={(e) => e.preventDefault()}>
  <div class="panel-head"><h2>Sample answers</h2></div>
  <p class="how">Change an answer and the pages update. {hiddenCount ? `${hiddenCount} question${hiddenCount === 1 ? ' is' : 's are'} hidden by a rule.` : ''}</p>
  <div class="panel-body">
    {#each visible as q (q.id)}
      {@const id = `ans-${q.key}`}
      {#if q.type === 'yesno'}
        <fieldset class="yesno">
          <legend>{q.label}{q.required ? ' *' : ''}</legend>
          <label class="check"><input type="radio" name={id} checked={doc.answers[q.key] === true} onchange={() => set(q.key, true)} /> Yes</label>
          <label class="check"><input type="radio" name={id} checked={doc.answers[q.key] === false} onchange={() => set(q.key, false)} /> No</label>
        </fieldset>
      {:else if q.type === 'repeating'}
        <fieldset class="repeat">
          <legend>{q.label}</legend>
          {#each rows(q.key) as row, i (i)}
            <div class="row" style="grid-template-columns: {q.columns.map((c) => WIDTHS[c.type] ?? '1fr').join(' ')} auto">
              {#each q.columns as col (col.key)}
                <input class="input" class:mono={col.type === 'ip'} aria-label="{col.label}, row {i + 1}" inputmode={col.type === 'number' ? 'numeric' : undefined}
                  value={row[col.key] ?? ''} oninput={(e) => setCell(q, i, col, e.currentTarget.value)} />
              {/each}
              <button type="button" class="btn quiet remove" aria-label="Remove row {i + 1}" title="Remove row" onclick={() => removeRow(q, i)}>×</button>
            </div>
          {/each}
          <button type="button" class="btn add" onclick={() => addRow(q)}>Add row</button>
        </fieldset>
      {:else}
        <div class="field">
          <label for={id}>{q.label}{q.required ? ' *' : ''}</label>
          {#if q.type === 'longtext'}
            <textarea {id} class="input" value={doc.answers[q.key] ?? ''} oninput={(e) => set(q.key, e.currentTarget.value)}></textarea>
          {:else if q.type === 'dropdown'}
            <select {id} class="input" value={doc.answers[q.key] ?? ''} onchange={(e) => set(q.key, e.currentTarget.value)}>
              <option value="">Choose…</option>
              {#each q.options as o (o)}<option value={o}>{o}</option>{/each}
            </select>
          {:else if q.type === 'number'}
            <input {id} class="input" type="number" step="0.1" value={doc.answers[q.key] ?? ''}
              oninput={(e) => set(q.key, e.currentTarget.value === '' ? null : Number(e.currentTarget.value))} />
          {:else if q.type === 'datetime'}
            <input {id} class="input" type="datetime-local" value={doc.answers[q.key] ?? ''} oninput={(e) => set(q.key, e.currentTarget.value)} />
          {:else if q.type === 'secret'}
            <input {id} class="input mono" type="password" autocomplete="off" value={doc.answers[q.key] ?? ''} oninput={(e) => set(q.key, e.currentTarget.value)} />
          {:else}
            <input {id} class="input" class:mono={q.type === 'ip'} value={doc.answers[q.key] ?? ''} oninput={(e) => set(q.key, e.currentTarget.value)} />
          {/if}
          {#if q.help}<span class="hint">{q.help}</span>{/if}
          {#if !FIELD_TYPES[q.type]}<span class="hint">Unknown field type</span>{/if}
        </div>
      {/if}
    {/each}
  </div>
</form>

<style>
  .answers { position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto; }
  .how { margin: 0; padding: 0 16px 10px; font-size: 12px; color: var(--text-muted); }
  fieldset { margin: 0; padding: 0; border: 0; min-width: 0; }
  legend { padding: 0; margin-bottom: 6px; font-size: 12.5px; font-weight: 600; }
  .yesno { display: flex; flex-wrap: wrap; gap: 4px 16px; }
  .yesno legend { width: 100%; }
  .repeat { display: grid; gap: 6px; }
  .row { display: grid; gap: 4px; }
  .row .input { padding: 4px 6px; min-height: 32px; font-size: 12.5px; }
  .row .remove { min-height: 32px; width: 28px; padding: 0; justify-content: center; font-size: 16px; }
  .add { justify-self: start; }
  @media (max-width: 1180px) { .answers { position: static; max-height: none; } }
</style>
