<script>
  // Settings for one layout block. Everything a block has is printed in the PDF; rules decide when.
  import ConditionEditor from '../ConditionEditor.svelte'
  import Where from '../Where.svelte'
  import {BLOCK_TYPES, SIGNER_ROLES, templateAssets, context} from '../../lib/sample.js'
  import {TONES, calloutColours, isHex} from '../../lib/colour.js'
  import {doc, library, updateBlock, removeBlock} from '../../lib/state.svelte.js'

  let {block} = $props()
  const set = (patch) => updateBlock(block.id, patch)

  const variables = $derived([
    ...Object.entries(context).flatMap(([group, values]) => Object.keys(values).map((k) => `${group}.${k}`)),
    ...doc.questions.filter((q) => !['group', 'repeating', 'photo'].includes(q.type)).map((q) => `answers.${q.key}`),
    ...doc.computed.map((c) => c.name),
    ...library.vars.map((v) => `vars.${v.key}`),
  ])
  const insert = (field, name) => set({[field]: `${block[field] ?? ''}${block[field] ? ' ' : ''}{{${name}}}`})

  const repeating = $derived(doc.questions.filter((q) => q.type === 'repeating'))
  const photos = $derived(doc.questions.filter((q) => q.type === 'photo'))
  const tableQuestion = $derived(doc.questions.find((q) => q.key === block.question))
  const shownColumns = $derived(block.kind === 'table' ? (block.columns ?? tableQuestion?.columns.map((c) => c.key) ?? []) : [])
  function toggleColumn(key, on) {
    const all = tableQuestion?.columns.map((c) => c.key) ?? []
    const next = on ? all.filter((k) => shownColumns.includes(k) || k === key) : shownColumns.filter((k) => k !== key)
    set({columns: next})
  }
  function moveColumn(key, delta) {
    const list = [...shownColumns]
    const i = list.indexOf(key)
    const j = i + delta
    if (i < 0 || j < 0 || j >= list.length) return
    ;[list[i], list[j]] = [list[j], list[i]]
    set({columns: list})
  }

  const colours = $derived(block.kind === 'callout' ? calloutColours(block) : null)

  const setSigner = (i, patch) => set({signers: block.signers.map((s, j) => (j === i ? {...s, ...patch} : s))})
  const addSigner = () => set({signers: [...block.signers, {role: 'reviewer', label: 'Reviewer', style: 'handwritten'}]})
  const removeSigner = (i) => set({signers: block.signers.filter((_, j) => j !== i)})

  const setItem = (i, patch) => set({items: block.items.map((s, j) => (j === i ? {...s, ...patch} : s))})
</script>

<div class="panel-head">
  <h2>{BLOCK_TYPES[block.kind].label}</h2>
  <button type="button" class="btn quiet" onclick={() => removeBlock(block.id)}>Remove</button>
</div>
<div class="panel-body">
  <div class="group-head"><h3>Printed in the PDF</h3><Where pdf compact /></div>

  {#if block.kind === 'section'}
    <div class="field"><label for="s-title">Title</label>
      <input id="s-title" class="input" value={block.title} oninput={(e) => set({title: e.currentTarget.value})} /></div>
    <div class="field"><label for="s-intro">Introduction</label>
      <textarea id="s-intro" class="input" rows="3" value={block.intro ?? ''} oninput={(e) => set({intro: e.currentTarget.value})}></textarea>
      <span class="hint">A short description printed under the heading. Leave it empty for none.</span></div>
    <label class="check"><input type="checkbox" checked={block.newPage} onchange={(e) => set({newPage: e.currentTarget.checked})} /> Start on a new page</label>
    <label class="check"><input type="checkbox" checked={block.numbered !== false} onchange={(e) => set({numbered: e.currentTarget.checked})} /> Number the section</label>

  {:else if block.kind === 'heading'}
    <div class="field"><label for="s-text">Text</label>
      <input id="s-text" class="input" value={block.text} oninput={(e) => set({text: e.currentTarget.value})} /></div>

  {:else if block.kind === 'text'}
    <div class="field"><label for="s-body">Text</label>
      <textarea id="s-body" class="input" rows="5" value={block.text} oninput={(e) => set({text: e.currentTarget.value})}></textarea>
      <span class="hint">Names in double braces are filled in when the PDF is made.</span></div>
    <div class="inserts">
      <select class="input" aria-label="Insert a variable" value="" onchange={(e) => { if (e.currentTarget.value) insert('text', e.currentTarget.value); e.currentTarget.value = '' }}>
        <option value="">Insert a variable…</option>
        {#each variables as v (v)}<option value={v}>{v}</option>{/each}
      </select>
      <select class="input" aria-label="Insert a text snippet" value="" onchange={(e) => { if (e.currentTarget.value) insert('text', e.currentTarget.value); e.currentTarget.value = '' }}>
        <option value="">Insert a text snippet…</option>
        {#each library.text as t (t.key)}<option value="text.{t.key}">text.{t.key}</option>{/each}
      </select>
    </div>

  {:else if block.kind === 'answer'}
    <div class="field"><label for="s-q">Question</label>
      <select id="s-q" class="input" value={block.question} onchange={(e) => set({question: e.currentTarget.value})}>
        {#each doc.questions.filter((q) => !['group', 'repeating'].includes(q.type)) as q (q.id)}<option value={q.key}>{q.label}</option>{/each}
      </select></div>
    <label class="check"><input type="checkbox" checked={block.showLabel} onchange={(e) => set({showLabel: e.currentTarget.checked})} /> Print the question above the answer</label>

  {:else if block.kind === 'table'}
    <div class="field"><label for="s-q">Rows from</label>
      <select id="s-q" class="input" value={block.question} onchange={(e) => set({question: e.currentTarget.value, columns: null})}>
        {#each repeating as q (q.id)}<option value={q.key}>{q.label}</option>{/each}
      </select></div>
    <div class="field"><label for="s-cap">Caption</label>
      <input id="s-cap" class="input" value={block.caption ?? ''} oninput={(e) => set({caption: e.currentTarget.value})} />
      <span class="hint">Printed above the table as “Table 1. …”. Tables are numbered in order.</span></div>
    {#if tableQuestion}
      <fieldset class="list">
        <legend>Columns, in order</legend>
        {#each [...shownColumns.map((k) => tableQuestion.columns.find((c) => c.key === k)).filter(Boolean), ...tableQuestion.columns.filter((c) => !shownColumns.includes(c.key))] as c (c.key)}
          {@const on = shownColumns.includes(c.key)}
          <div class="list-row">
            <label class="check"><input type="checkbox" checked={on} disabled={on && shownColumns.length === 1} onchange={(e) => toggleColumn(c.key, e.currentTarget.checked)} /> {c.label}</label>
            {#if on}
              <span class="order">
                <button type="button" class="btn quiet mini" aria-label="Move {c.label} earlier" onclick={() => moveColumn(c.key, -1)}>↑</button>
                <button type="button" class="btn quiet mini" aria-label="Move {c.label} later" onclick={() => moveColumn(c.key, 1)}>↓</button>
              </span>
            {/if}
          </div>
        {/each}
      </fieldset>
    {/if}
    <div class="field"><label for="s-empty">Text when there are no rows</label>
      <input id="s-empty" class="input" value={block.emptyText ?? ''} oninput={(e) => set({emptyText: e.currentTarget.value})} /></div>
    <p class="note">Rows never split across pages, and the header row repeats on each page.</p>

  {:else if block.kind === 'image'}
    <div class="field"><label for="s-src">Image</label>
      <select id="s-src" class="input" value={block.source} onchange={(e) => set({source: e.currentTarget.value})}>
        <option value="template">Uploaded with the template</option>
        <option value="question">A photo the technician adds</option>
      </select></div>
    {#if block.source === 'template'}
      <div class="field"><label for="s-asset">File</label>
        <select id="s-asset" class="input" value={block.asset} onchange={(e) => set({asset: e.currentTarget.value})}>
          {#each Object.entries(templateAssets) as [key, a] (key)}<option value={key}>{a.label}</option>{/each}
        </select>
        <span class="hint">In Skjald you upload PNG, JPEG or SVG here; SVGs are cleaned of scripts.</span></div>
    {:else}
      <div class="field"><label for="s-photo">Photo question</label>
        <select id="s-photo" class="input" value={block.question} onchange={(e) => set({question: e.currentTarget.value})}>
          <option value="">Choose…</option>
          {#each photos as q (q.id)}<option value={q.key}>{q.label}</option>{/each}
        </select>
        {#if !photos.length}<span class="hint">Add a Photo field on the Questions tab first.</span>{/if}</div>
    {/if}
    <div class="field"><label for="s-cap">Caption</label>
      <input id="s-cap" class="input" value={block.caption ?? ''} oninput={(e) => set({caption: e.currentTarget.value})} />
      <span class="hint">Printed under the image as “Figure 1. …”.</span></div>
    <div class="field"><label for="s-width">Width</label>
      <select id="s-width" class="input" value={block.width} onchange={(e) => set({width: e.currentTarget.value})}>
        <option value="full">Full width</option><option value="half">Half width</option><option value="third">A third</option>
      </select></div>

  {:else if block.kind === 'callout'}
    <div class="field"><span class="label" id="s-tone-label">Colour</span>
      <div class="tones" role="radiogroup" aria-labelledby="s-tone-label">
        {#each Object.entries(TONES) as [key, t] (key)}
          <label class="tone" style="--t-bg: {t.bg}; --t-fg: {t.fg}; --t-border: {t.border}">
            <input type="radio" name="tone-{block.id}" value={key} checked={block.tone === key} onchange={() => set({tone: key})} /><span>{t.label}</span>
          </label>
        {/each}
        <label class="tone custom">
          <input type="radio" name="tone-{block.id}" value="custom" checked={block.tone === 'custom'} onchange={() => set({tone: 'custom'})} /><span>Custom</span>
        </label>
      </div>
      <span class="hint">The named colours come from the report style. Custom is for report designers.</span></div>
    {#if block.tone === 'custom'}
      <div class="field"><label for="s-colour">Custom background</label>
        <div class="colour-row">
          <input id="s-colour" type="color" value={isHex(block.color) ? block.color : '#DCE6EE'} oninput={(e) => set({color: e.currentTarget.value.toUpperCase()})} />
          <input class="input mono" aria-label="Hex colour" value={block.color} oninput={(e) => set({color: e.currentTarget.value})} />
        </div>
        {#if colours}
          {#if colours.ok}<span class="pill ok">Readable: contrast {colours.ratio}:1</span>
          {:else}<span class="pill warning wrap">Hard to read: contrast {colours.ratio}:1, needs 4.5:1. Pick a lighter or darker colour.</span>{/if}
        {/if}
      </div>
    {/if}
    <div class="field"><label for="s-ctitle">Title</label>
      <input id="s-ctitle" class="input" value={block.title ?? ''} oninput={(e) => set({title: e.currentTarget.value})} /></div>
    <div class="field"><label for="s-body">Text</label>
      <textarea id="s-body" class="input" rows="3" value={block.text} oninput={(e) => set({text: e.currentTarget.value})}></textarea></div>

  {:else if block.kind === 'sources'}
    <div class="field"><label for="s-intro">Introduction</label>
      <input id="s-intro" class="input" value={block.intro ?? ''} oninput={(e) => set({intro: e.currentTarget.value})} /></div>
    <fieldset class="list">
      <legend>Sources every report gets</legend>
      {#each block.items as s, i (i)}
        <div class="source">
          <input class="input" aria-label="Source {i + 1} title" value={s.title} oninput={(e) => setItem(i, {title: e.currentTarget.value})} />
          <input class="input mono" aria-label="Source {i + 1} link" value={s.link} oninput={(e) => setItem(i, {link: e.currentTarget.value})} />
          <button type="button" class="btn quiet" aria-label="Remove source {i + 1}" onclick={() => set({items: block.items.filter((_, j) => j !== i)})}>Remove</button>
        </div>
      {/each}
      <button type="button" class="btn" onclick={() => set({items: [...block.items, {title: '', link: ''}]})}>Add a source</button>
    </fieldset>
    <div class="field"><label for="s-srcq">Then add the technician's sources from</label>
      <select id="s-srcq" class="input" value={block.question} onchange={(e) => set({question: e.currentTarget.value})}>
        <option value="">Nowhere: only the sources above</option>
        {#each repeating as q (q.id)}<option value={q.key}>{q.label}</option>{/each}
      </select>
      <span class="hint">A repeating group with a title and a link column.</span></div>

  {:else if block.kind === 'signatures'}
    <fieldset class="list">
      <legend>Signature boxes ({block.signers.length} of 4)</legend>
      {#each block.signers as s, i (i)}
        <div class="signer">
          <select class="input" aria-label="Box {i + 1}: who signs" value={s.role} onchange={(e) => setSigner(i, {role: e.currentTarget.value, label: SIGNER_ROLES[e.currentTarget.value], style: e.currentTarget.value === 'company' ? 'stamp' : s.style})}>
            {#each Object.entries(SIGNER_ROLES) as [k, v] (k)}<option value={k}>{v}</option>{/each}
          </select>
          <select class="input" aria-label="Box {i + 1}: style" value={s.style} onchange={(e) => setSigner(i, {style: e.currentTarget.value})}>
            <option value="handwritten">Handwritten</option><option value="stamp">Stamp</option>
          </select>
          <input class="input" aria-label="Box {i + 1}: label" value={s.label} oninput={(e) => setSigner(i, {label: e.currentTarget.value})} />
          <button type="button" class="btn quiet" aria-label="Remove box {i + 1}" disabled={block.signers.length === 1} onclick={() => removeSigner(i)}>×</button>
        </div>
      {/each}
      <button type="button" class="btn" disabled={block.signers.length >= 4} onclick={addSigner}>Add a signature box</button>
    </fieldset>
    <div class="field"><label for="s-layout">Layout</label>
      <select id="s-layout" class="input" value={block.layout} onchange={(e) => set({layout: e.currentTarget.value})}>
        <option value="row">Side by side</option><option value="stacked">One under the other</option>
      </select></div>
    <label class="check"><input type="checkbox" checked={block.showDate} onchange={(e) => set({showDate: e.currentTarget.checked})} /> Print the signing date</label>
    <p class="note">Who must sign, and in which order, is set in the template's signing policy. These boxes are where the signatures appear.</p>

  {:else if block.kind === 'pagebreak'}
    <p class="note">Everything after this block starts on a new page.</p>
  {/if}

  <div class="group-head"><h3>When it appears</h3></div>
  <ConditionEditor idPrefix="block" rule={block.showWhen} onchange={(rule) => set({showWhen: rule})} />
</div>

<style>
  .group-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-top: 10px; border-top: 1px solid var(--border); }
  .group-head:first-child { padding-top: 0; border-top: 0; }
  .group-head h3 { margin: 0; font-family: var(--font-sans); font-size: 12px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); }
  .inserts { display: grid; gap: 6px; }
  .inserts .input { font-size: 12.5px; color: var(--text-muted); }
  .list { display: grid; gap: 6px; margin: 0; padding: 10px 12px 12px; border: 1px solid var(--border); border-radius: var(--radius-md); min-width: 0; }
  legend { padding: 0 4px; font-size: 12.5px; font-weight: 600; }
  .list > .btn { justify-self: start; }
  .list-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
  .order { display: inline-flex; gap: 2px; }
  .mini { min-height: 28px; padding: 0 8px; }
  .source { display: grid; gap: 4px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
  .source .btn { justify-self: start; }
  .signer { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 4px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
  .signer .input:nth-child(3) { grid-column: 1 / 2; }
  .tones { display: flex; flex-wrap: wrap; gap: 6px; }
  .tone { position: relative; display: inline-flex; }
  .tone input { position: absolute; opacity: 0; inset: 0; margin: 0; cursor: pointer; }
  .tone span { display: inline-flex; align-items: center; min-height: 30px; padding: 0 10px; border-radius: var(--radius-sm);
    border: 1px solid var(--t-border, var(--border-strong)); background: var(--t-bg, var(--surface)); color: var(--t-fg, var(--text)); font-size: 12.5px; font-weight: 600; }
  .tone input:checked + span { box-shadow: 0 0 0 2px var(--surface), 0 0 0 4px var(--link); }
  .tone input:focus-visible + span { outline: 2px solid var(--link); outline-offset: 4px; }
  .colour-row { display: flex; gap: 6px; align-items: center; }
  .colour-row input[type='color'] { width: 44px; height: 36px; padding: 2px; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: var(--surface); }
  .note { margin: 0; color: var(--text-muted); font-size: 12.5px; }
</style>
