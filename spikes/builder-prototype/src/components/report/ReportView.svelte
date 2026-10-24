<script>
  // The technician's screen: the form, one step at a time, with the PDF the customer will get next to it.
  import PdfPages from './PdfPages.svelte'
  import SecretField from './SecretField.svelte'
  import Where from '../Where.svelte'
  import {context, FIELD_TYPES} from '../../lib/sample.js'
  import {interpolate, isIpAddress} from '../../lib/pages.js'
  import {doc, library, session, templateData, ruleResult, currentUser, log} from '../../lib/state.svelte.js'

  let {preview = false} = $props()

  const data = $derived(templateData(doc.answers))
  const visible = (q) => ruleResult(q.showWhen, data).value !== false

  // Questions before the first "Form step" go into a first step of their own.
  const steps = $derived.by(() => {
    const list = []
    let current = null
    for (const q of doc.questions) {
      if (q.type === 'group') {
        current = {id: q.id, title: q.label, help: q.help, questions: []}
        list.push(current)
      } else {
        if (!current) list.push((current = {id: 'first', title: 'Questions', help: '', questions: []}))
        current.questions.push(q)
      }
    }
    return list
  })

  let stepIndex = $state(0)
  let showPdf = $state(false)
  let pageInfo = $state({total: 0, hidden: 0})
  const reviewIndex = $derived(steps.length)
  const step = $derived(steps[Math.min(stepIndex, steps.length - 1)])

  const isEmpty = (q, v) => v === undefined || v === null || v === '' || (q.type === 'repeating' && Array.isArray(v) && v.length === 0)
  const missingIn = (s) => s.questions.filter((q) => q.required && visible(q) && isEmpty(q, doc.answers[q.key]))
  const missing = $derived(steps.flatMap(missingIn))
  const problems = $derived(doc.questions.filter((q) => visible(q) && problemOf(q)))

  function problemOf(q) {
    const v = doc.answers[q.key]
    if (q.type === 'ip' && v && !isIpAddress(v)) return 'Enter an IPv4 or IPv6 address, like 198.51.100.23.'
    if (q.type === 'repeating' && Array.isArray(v)) {
      const bad = q.columns.filter((c) => c.type === 'ip').some((c) => v.some((r) => r[c.key] && !isIpAddress(r[c.key])))
      if (bad) return 'One of the addresses is not a valid IPv4 or IPv6 address.'
    }
    return ''
  }

  const set = (key, value) => (doc.answers[key] = value)
  const rows = (key) => (Array.isArray(doc.answers[key]) ? doc.answers[key] : [])
  function setCell(q, i, col, value) {
    const v = col.type === 'number' && value.trim() !== '' && Number.isFinite(Number(value)) ? Number(value) : value
    doc.answers[q.key] = rows(q.key).map((r, j) => (j === i ? {...r, [col.key]: v} : r))
  }
  const addRow = (q) => (doc.answers[q.key] = [...rows(q.key), Object.fromEntries(q.columns.map((c) => [c.key, c.type === 'number' ? 0 : '']))])
  const removeRow = (q, i) => (doc.answers[q.key] = rows(q.key).filter((_, j) => j !== i))
  const WIDTHS = {ip: 'minmax(0, 1.9fr)', number: 'minmax(0, 1fr)', text: 'minmax(0, 1.4fr)', datetime: 'minmax(0, 1.4fr)'}

  function insertSnippet(q, key) {
    const snippet = library.text.find((t) => t.key === key)
    if (!snippet) return
    const text = interpolate(snippet.value, data, doc.questions).map((p) => p.text).join('')
    const current = doc.answers[q.key] ?? ''
    set(q.key, current ? `${current.trimEnd()} ${text}` : text)
    log(`Inserted the text snippet text.${key} into “${q.label}”`)
  }

  let photoError = $state('')
  function readPhoto(q, file) {
    photoError = ''
    if (!file) return
    if (!file.type.startsWith('image/')) return (photoError = 'Choose an image file.')
    if (file.size > 8 * 1024 * 1024) return (photoError = 'Photos can be up to 8 MB in the prototype.')
    const reader = new FileReader()
    reader.onload = () => set(q.key, reader.result)
    reader.readAsDataURL(file)
  }

  function go(i) {
    stepIndex = Math.max(0, Math.min(i, reviewIndex))
  }
  function send() {
    session.notice = missing.length
      ? `Fill in ${missing.length} required answer${missing.length === 1 ? '' : 's'} first.`
      : 'Prototype: nothing is sent. In Skjald the report now goes to the reviewer, and your checkout is released.'
  }
  const time = (iso) => new Date(iso).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'})
</script>

<div class="report" class:with-pdf={showPdf}>
  {#if preview}
    <div class="explain">
      <strong>This is what a technician sees.</strong>
      <span>They fill in the form on the left; the customer receives the PDF on the right. The answers are samples, so you can try the rules.</span>
      <Where form pdf />
    </div>
  {/if}

  <header class="head">
    <nav class="crumbs" aria-label="Breadcrumb"><span>Reports</span><span aria-hidden="true">›</span><span>{context.customer.name}</span><span aria-hidden="true">›</span><span>{context.project.number}</span></nav>
    <div class="title-row">
      <h1>{context.report.number}</h1>
      <span class="pill plain">Draft</span>
      <span class="pill info">Checked out by {preview ? 'the technician' : 'you'}</span>
    </div>
    <p class="meta">Security incident report · template version {preview ? '4 (draft)' : '3'} · technician {context.report.technician}, reviewer {context.report.reviewer}</p>
  </header>

  <div class="work">
    <section class="form-col" aria-label="Report form">
      <ol class="steps" aria-label="Steps">
        {#each steps as s, i (s.id)}
          {@const left = missingIn(s).length}
          <li><button type="button" class:current={stepIndex === i} aria-current={stepIndex === i ? 'step' : undefined} onclick={() => go(i)}>
            <span class="n">{i + 1}</span><span class="t">{s.title}</span>{#if left}<span class="left">{left} to do</span>{:else}<span class="done" aria-label="complete">✓</span>{/if}
          </button></li>
        {/each}
        <li><button type="button" class:current={stepIndex === reviewIndex} onclick={() => go(reviewIndex)}><span class="n">{steps.length + 1}</span><span class="t">Review and send</span></button></li>
      </ol>

      <form class="panel step" onsubmit={(e) => e.preventDefault()}>
        {#if stepIndex < reviewIndex && step}
          <div class="panel-head"><h2>{step.title}</h2></div>
          {#if step.help}<p class="step-help">{step.help}</p>{/if}
          <div class="panel-body">
            {#each step.questions.filter(visible) as q (q.id)}
              {@const id = `ans-${q.key}`}
              {@const problem = problemOf(q)}
              {#if q.type === 'yesno'}
                <fieldset class="yesno">
                  <legend>{q.label}{q.required ? ' *' : ''}</legend>
                  {#if q.help}<span class="hint">{q.help}</span>{/if}
                  <label class="check"><input type="radio" name={id} checked={doc.answers[q.key] === true} onchange={() => set(q.key, true)} /> Yes</label>
                  <label class="check"><input type="radio" name={id} checked={doc.answers[q.key] === false} onchange={() => set(q.key, false)} /> No</label>
                </fieldset>
              {:else if q.type === 'repeating'}
                <fieldset class="repeat">
                  <legend>{q.label}{q.required ? ' *' : ''}</legend>
                  {#if q.help}<span class="hint">{q.help}</span>{/if}
                  <div class="row head-row" style="grid-template-columns: {q.columns.map((c) => WIDTHS[c.type] ?? '1fr').join(' ')} 30px" aria-hidden="true">
                    {#each q.columns as col (col.key)}<span>{col.label}</span>{/each}
                  </div>
                  {#each rows(q.key) as row, i (i)}
                    <div class="row" style="grid-template-columns: {q.columns.map((c) => WIDTHS[c.type] ?? '1fr').join(' ')} 30px">
                      {#each q.columns as col (col.key)}
                        <input class="input" class:mono={col.type === 'ip'} class:invalid={col.type === 'ip' && row[col.key] && !isIpAddress(row[col.key])}
                          aria-label="{col.label}, row {i + 1}" inputmode={col.type === 'number' ? 'numeric' : undefined}
                          value={row[col.key] ?? ''} oninput={(e) => setCell(q, i, col, e.currentTarget.value)} />
                      {/each}
                      <button type="button" class="btn quiet remove" aria-label="Remove row {i + 1}" title="Remove row" onclick={() => removeRow(q, i)}>×</button>
                    </div>
                  {/each}
                  <button type="button" class="btn add" onclick={() => addRow(q)}>Add row</button>
                  {#if problem}<span class="error" role="alert">{problem}</span>{/if}
                </fieldset>
              {:else}
                <div class="field">
                  {#if q.type === 'photo'}<span class="label">{q.label}{q.required ? ' *' : ''}</span>{:else}<label for={id}>{q.label}{q.required ? ' *' : ''}</label>{/if}
                  {#if q.help}<span class="hint" id="{id}-help">{q.help}</span>{/if}
                  {#if q.type === 'longtext'}
                    <textarea {id} class="input" rows="4" value={doc.answers[q.key] ?? ''} oninput={(e) => set(q.key, e.currentTarget.value)}></textarea>
                    <select class="input snippet" aria-label="Insert a text snippet from the library" value="" onchange={(e) => { insertSnippet(q, e.currentTarget.value); e.currentTarget.value = '' }}>
                      <option value="">Insert a text snippet…</option>
                      {#each library.text as t (t.key)}<option value={t.key}>{t.key.replaceAll('_', ' ')}: {t.about}</option>{/each}
                    </select>
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
                    <SecretField question={q} value={doc.answers[q.key]} onchange={(v) => set(q.key, v)} />
                  {:else if q.type === 'photo'}
                    <div class="photo">
                      {#if doc.answers[q.key]}<img src={doc.answers[q.key]} alt="{q.label}, uploaded" />{/if}
                      <div class="photo-actions">
                        <input {id} class="file-input" type="file" accept="image/*" onchange={(e) => readPhoto(q, e.currentTarget.files?.[0])} />
                        <label for={id} class="btn file-button">{doc.answers[q.key] ? 'Replace the photo' : 'Choose a photo'}</label>
                        {#if doc.answers[q.key]}<button type="button" class="btn quiet" onclick={() => set(q.key, '')}>Remove photo</button>{/if}
                      </div>
                      {#if photoError}<span class="error" role="alert">{photoError}</span>{/if}
                    </div>
                  {:else}
                    <input {id} class="input" class:mono={q.type === 'ip'} class:invalid={!!problem} value={doc.answers[q.key] ?? ''} oninput={(e) => set(q.key, e.currentTarget.value)} />
                  {/if}
                  {#if problem && q.type !== 'repeating'}<span class="error" role="alert">{problem}</span>{/if}
                  {#if !FIELD_TYPES[q.type]}<span class="hint">Unknown field type</span>{/if}
                </div>
              {/if}
            {:else}
              <p class="note">Nothing to fill in on this step with the current answers.</p>
            {/each}
          </div>
          <div class="step-nav">
            <button type="button" class="btn" disabled={stepIndex === 0} onclick={() => go(stepIndex - 1)}>Previous</button>
            <button type="button" class="btn primary" onclick={() => go(stepIndex + 1)}>{stepIndex === reviewIndex - 1 ? 'Review' : 'Next step'}</button>
          </div>
        {:else}
          <div class="panel-head"><h2>Review and send</h2></div>
          <div class="panel-body">
            <ul class="checklist">
              <li>{#if missing.length}<span class="pill warning">{missing.length} to do</span> Required answers missing: {missing.map((q) => q.label).join(', ')}.{:else}<span class="pill ok">Done</span> All required answers are filled in.{/if}</li>
              <li>{#if problems.length}<span class="pill critical">Check</span> {problems.map((q) => q.label).join(', ')} {problems.length === 1 ? 'has' : 'have'} an invalid value.{:else}<span class="pill ok">Done</span> No invalid values.{/if}</li>
              <li><span class="pill plain">PDF</span> {pageInfo.total} pages{pageInfo.hidden ? `; ${pageInfo.hidden} blocks are left out by rules` : ''}.</li>
            </ul>
            <p class="note">After you send it, the reviewer either asks for changes or approves it. Then it is signed: by you first, then the reviewer, then the company seal.</p>
            {#if session.activity.length}
              <div class="activity">
                <span class="overline">Logged during this visit</span>
                <ul>{#each session.activity as a, i (i)}<li><span class="mono">{time(a.at)}</span> {a.by}: {a.change}</li>{/each}</ul>
              </div>
            {/if}
          </div>
          <div class="step-nav">
            <button type="button" class="btn" onclick={() => go(reviewIndex - 1)}>Previous</button>
            <button type="button" class="btn accent" onclick={send}>Send for review</button>
          </div>
        {/if}
      </form>
      <button type="button" class="btn pdf-toggle" aria-expanded={showPdf} onclick={() => (showPdf = !showPdf)}>{showPdf ? 'Hide the PDF' : `Show the PDF (${pageInfo.total} pages)`}</button>
    </section>

    <section class="pdf-col" aria-label="PDF preview">
      <div class="pdf-head"><h2>The PDF</h2><span class="sub">What {context.customer.name} receives. Updates as you type.</span></div>
      <PdfPages answers={doc.answers} onpages={(info) => (pageInfo = info)} />
    </section>
  </div>
</div>

<style>
  .report { display: grid; gap: 14px; }
  .explain { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; padding: 10px 14px; border-radius: var(--radius-md);
    background: var(--info-bg); color: var(--info-text); font-size: 13px; }
  .explain span { max-width: 80ch; }
  .head { display: grid; gap: 2px; }
  .crumbs { display: flex; flex-wrap: wrap; gap: 6px; font-size: 12.5px; color: var(--text-muted); }
  .title-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; }
  h1 { font-size: 26px; font-family: var(--font-display); font-weight: 400; margin: 0; }
  .meta { margin: 0; font-size: 13px; color: var(--text-muted); }
  .work { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.05fr); gap: 20px; align-items: start; }
  .form-col { display: grid; gap: 12px; min-width: 0; }
  .steps { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
  .steps button { display: inline-flex; align-items: center; gap: 8px; min-height: 36px; padding: 0 12px 0 6px; border: 1px solid var(--border);
    border-radius: var(--radius-pill); background: var(--surface); color: var(--text); font-size: 13px; font-weight: 600; cursor: pointer; }
  .steps button.current { border-color: var(--text); box-shadow: 0 0 0 1px var(--text); }
  .n { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: var(--surface-subtle); font-size: 12px; }
  .left { font-size: 11.5px; font-weight: 600; color: var(--warning-text); }
  .done { font-size: 12px; color: var(--ok-text); }
  .step-help { margin: -4px 0 0; padding: 0 16px 12px; font-size: 13px; color: var(--text-muted); max-width: 68ch; }
  .step-nav { display: flex; justify-content: space-between; gap: 8px; padding: 0 16px 16px; }
  fieldset { margin: 0; padding: 0; border: 0; min-width: 0; display: grid; gap: 6px; }
  legend { padding: 0; margin-bottom: 4px; font-size: 12.5px; font-weight: 600; }
  .yesno { display: flex; flex-wrap: wrap; gap: 4px 16px; }
  .yesno legend, .yesno .hint { width: 100%; }
  .row { display: grid; gap: 4px; }
  .head-row span { font-size: 11.5px; font-weight: 600; color: var(--text-muted); }
  .row .input { padding: 4px 6px; min-height: 32px; font-size: 12.5px; }
  .remove { min-height: 32px; width: 30px; padding: 0; justify-content: center; font-size: 16px; }
  .add { justify-self: start; }
  .input.invalid { border-color: var(--critical-text); box-shadow: 0 0 0 1px var(--critical-text); }
  .error { font-size: 12px; color: var(--critical-text); }
  .snippet { font-size: 12.5px; color: var(--text-muted); }
  .photo { display: grid; gap: 6px; }
  .photo img { max-width: 100%; max-height: 180px; object-fit: contain; justify-self: start; border: 1px solid var(--border); border-radius: var(--radius-sm); background: #FFFFFF; }
  .photo-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  /* The native file input is hidden but stays focusable; its label is the visible button. */
  .file-input { position: absolute; width: 1px; height: 1px; opacity: 0; overflow: hidden; }
  .file-input:focus-visible + .file-button { outline: 2px solid var(--link); outline-offset: 2px; }
  .note { margin: 0; color: var(--text-muted); font-size: 13px; }
  .checklist { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; font-size: 13.5px; }
  .checklist .pill { margin-right: 6px; }
  .activity { display: grid; gap: 4px; padding: 10px 12px; border-radius: var(--radius-md); background: var(--surface-subtle); }
  .activity ul { margin: 0; padding-left: 18px; font-size: 12.5px; }
  .pdf-col { display: grid; gap: 10px; min-width: 0; position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto; padding: 2px 6px 6px 2px; }
  .pdf-head { display: grid; gap: 2px; }
  .pdf-head h2 { font-size: 20px; }
  .sub { font-size: 12.5px; color: var(--text-muted); }
  .pdf-toggle { display: none; justify-self: start; }
  @media (max-width: 1100px) {
    .work { grid-template-columns: minmax(0, 1fr); }
    .pdf-col { position: static; max-height: none; overflow: visible; display: none; }
    .with-pdf .pdf-col { display: grid; }
    .pdf-toggle { display: inline-flex; }
  }
</style>
