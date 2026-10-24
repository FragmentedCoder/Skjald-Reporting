<script>
  import {dndzone} from 'svelte-dnd-action'
  import Palette from './Palette.svelte'
  import ConditionEditor from './ConditionEditor.svelte'
  import {BLOCK_TYPES, newBlock, context} from '../lib/sample.js'
  import {describeRule} from '../lib/cel.js'
  import {doc, updateBlock, removeBlock} from '../lib/state.svelte.js'

  const GLYPHS = {section: '§', heading: 'H', text: 'T', answer: 'A', table: '⊞', callout: '▭', pagebreak: '⤓', signatures: '✍'}
  const paletteEntries = Object.entries(BLOCK_TYPES).map(([kind, t]) => ({id: `pal-${kind}`, kind, label: t.label, hint: t.hint, glyph: GLYPHS[kind]}))

  const selected = $derived(doc.blocks.find((b) => b.id === doc.selectedBlock))
  const variables = $derived([
    ...Object.entries(context).flatMap(([group, values]) => Object.keys(values).map((k) => `${group}.${k}`)),
    ...doc.questions.filter((q) => q.type !== 'repeating').map((q) => `answers.${q.key}`),
    ...doc.computed.map((c) => c.name),
  ])

  // Section number for each block, so the canvas shows the report's structure.
  const sectionOf = $derived.by(() => {
    const map = {}
    let n = 0
    for (const b of doc.blocks) {
      if (b.kind === 'section') n += 1
      map[b.id] = n
    }
    return map
  })

  function materialise(items) {
    // Items dragged in from the palette become real blocks with fresh ids.
    let fresh = null
    const next = items.map((item) => {
      if (!item.palette) return item
      fresh = newBlock(item.kind)
      return fresh
    })
    return {next, fresh}
  }

  function consider(e) {
    doc.blocks = e.detail.items
  }
  function finalize(e) {
    const {next, fresh} = materialise(e.detail.items)
    doc.blocks = next
    if (fresh) doc.selectedBlock = fresh.id
  }
  function addAfterSelected(kind) {
    const block = newBlock(kind)
    const index = doc.blocks.findIndex((b) => b.id === doc.selectedBlock)
    const next = [...doc.blocks]
    next.splice(index + 1, 0, block)
    doc.blocks = next
    doc.selectedBlock = block.id
  }
  const questionLabel = (key) => doc.questions.find((q) => q.key === key)?.label ?? 'Removed question'
  const columns = (key) => doc.questions.find((q) => q.key === key)?.columns ?? []
  const parts = (text) => String(text ?? '').split(/(\{\{\s*[\w.]+\s*\}\})/g)
</script>

<div class="workspace">
  <Palette entries={paletteEntries} type="blocks" title="Blocks" onadd={addAfterSelected} />

  <section class="canvas" aria-label="Report layout">
    <div class="paper">
      <div class="cover" aria-hidden="true">
        <span class="overline">Cover · filled automatically</span>
        <span class="cover-title">Security incident report</span>
        <span class="cover-meta">{context.customer.name} · {context.report.number} · key facts table</span>
      </div>
      <div
        class="blocks"
        use:dndzone={{items: doc.blocks, type: 'blocks', flipDurationMs: 150, dropTargetStyle: {outline: '2px dashed var(--link)', outlineOffset: '4px'}}}
        onconsider={consider}
        onfinalize={finalize}
      >
        {#each doc.blocks as block (block.id)}
          <div class="block kind-{block.kind}" class:selected={block.id === doc.selectedBlock} class:inside={block.kind !== 'section' && sectionOf[block.id] > 0}>
            <button type="button" class="pick" onclick={() => (doc.selectedBlock = block.id)} aria-label="Edit {BLOCK_TYPES[block.kind]?.label ?? 'block'}"><span class="hit"></span></button>
            {#if block.kind === 'section'}
              <div class="section-head">
                <span class="overline">Section {sectionOf[block.id]}</span>
                <h3>{block.title}</h3>
              </div>
              <div class="chips">
                {#if block.newPage}<span class="pill info">Starts a new page</span>{/if}
                {#if block.showWhen}<span class="pill warning wrap">Only when: {describeRule(block.showWhen, doc.questions)}</span>{/if}
              </div>
            {:else if block.kind === 'heading'}
              <h4>{block.text}</h4>
            {:else if block.kind === 'text' || block.kind === 'callout'}
              <p class:callout={block.kind === 'callout'}>
                {#each parts(block.text) as part, i (i)}{#if part.startsWith('{{')}<span class="var mono">{part.replace(/[{}\s]/g, '')}</span>{:else}{part}{/if}{/each}
              </p>
            {:else if block.kind === 'answer'}
              <div class="answer"><span class="overline">Answer</span><span>{questionLabel(block.question)}</span></div>
            {:else if block.kind === 'table'}
              <div class="mini-table" style="--cols: {columns(block.question).length || 1}">
                {#each columns(block.question) as c (c.key)}<span>{c.label}</span>{/each}
              </div>
              <span class="caption">One row per entry in “{questionLabel(block.question)}”</span>
            {:else if block.kind === 'pagebreak'}
              <div class="break"><span>Page break</span></div>
            {:else if block.kind === 'signatures'}
              <div class="sigs">
                <span class="sig hand">Technician</span><span class="sig hand">Reviewer</span><span class="sig stamp">Company seal</span>
              </div>
            {/if}
            {#if block.kind !== 'section' && block.showWhen}
              <span class="pill warning wrap when">Only when: {describeRule(block.showWhen, doc.questions)}</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  </section>

  <aside class="panel props" aria-label="Properties">
    {#if selected}
      <div class="panel-head">
        <h2>{BLOCK_TYPES[selected.kind].label}</h2>
        <button type="button" class="btn quiet" onclick={() => removeBlock(selected.id)}>Remove</button>
      </div>
      <div class="panel-body">
        {#if selected.kind === 'section'}
          <div class="field"><label for="p-title">Title</label>
            <input id="p-title" class="input" value={selected.title} oninput={(e) => updateBlock(selected.id, {title: e.currentTarget.value})} /></div>
          <label class="check"><input id="p-newpage" type="checkbox" checked={selected.newPage}
            onchange={(e) => updateBlock(selected.id, {newPage: e.currentTarget.checked})} /> Start on a new page</label>
        {:else if selected.kind === 'heading'}
          <div class="field"><label for="p-text">Text</label>
            <input id="p-text" class="input" value={selected.text} oninput={(e) => updateBlock(selected.id, {text: e.currentTarget.value})} /></div>
        {:else if selected.kind === 'text' || selected.kind === 'callout'}
          <div class="field"><label for="p-body">Text</label>
            <textarea id="p-body" class="input" value={selected.text} oninput={(e) => updateBlock(selected.id, {text: e.currentTarget.value})}></textarea>
            <span class="hint">Variables in double braces are filled in when the report is generated.</span></div>
          <div class="field"><label for="p-var">Insert a variable</label>
            <select id="p-var" class="input" value="" onchange={(e) => { if (e.currentTarget.value) updateBlock(selected.id, {text: `${selected.text} {{${e.currentTarget.value}}}`}); e.currentTarget.value = '' }}>
              <option value="">Choose…</option>
              {#each variables as v (v)}<option value={v}>{v}</option>{/each}
            </select></div>
        {:else if selected.kind === 'answer' || selected.kind === 'table'}
          <div class="field"><label for="p-q">{selected.kind === 'table' ? 'Repeating group' : 'Question'}</label>
            <select id="p-q" class="input" value={selected.question} onchange={(e) => updateBlock(selected.id, {question: e.currentTarget.value})}>
              {#each doc.questions.filter((q) => (selected.kind === 'table') === (q.type === 'repeating')) as q (q.id)}<option value={q.key}>{q.label}</option>{/each}
            </select></div>
        {:else if selected.kind === 'pagebreak'}
          <p class="note">Everything after this block starts on a new page.</p>
        {:else if selected.kind === 'signatures'}
          <p class="note">Technician and reviewer sign in their handwritten style; the company seal is a stamp. Who signs is set in the template settings.</p>
        {/if}
        <ConditionEditor idPrefix="block" rule={selected.showWhen} onchange={(rule) => updateBlock(selected.id, {showWhen: rule})} />
      </div>
    {:else}
      <div class="panel-body"><p class="note">Select a block on the page to edit it.</p></div>
    {/if}
  </aside>
</div>

<style>
  .workspace { display: grid; grid-template-columns: 236px minmax(0, 1fr) 320px; gap: 16px; align-items: start; }
  .canvas { min-width: 0; }
  .paper { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 28px clamp(16px, 4vw, 44px) 36px; }
  .cover { display: grid; gap: 4px; padding: 14px 16px; margin-bottom: 16px; border-radius: var(--radius-md); background: var(--surface-subtle); }
  .cover-title { font-family: var(--font-display); font-size: 24px; }
  .cover-meta { font-size: 12.5px; color: var(--text-muted); }
  .blocks { display: grid; gap: 8px; min-height: 120px; }
  .block { position: relative; display: grid; gap: 6px; padding: 10px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); }
  .block.inside { margin-left: 18px; }
  .block.kind-section { margin-top: 10px; background: var(--surface-subtle); }
  .block.selected { border-color: var(--link); box-shadow: 0 0 0 1px var(--link); }
  .pick { position: absolute; inset: 0; border: 0; background: transparent; border-radius: inherit; cursor: pointer; }
  .pick:focus-visible { outline-offset: -2px; }
  /* svelte-dnd-action won't start a drag when the pressed element has a value (as buttons do), so a span inside takes the press. */
  .hit { position: absolute; inset: 0; border-radius: inherit; }
  .block > :not(.pick) { position: relative; pointer-events: none; }
  .section-head { display: grid; gap: 2px; }
  .section-head h3 { font-size: 20px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .when { justify-self: start; }
  h4 { margin: 0; font-family: var(--font-display); font-weight: 400; font-size: 16px; }
  p { margin: 0; max-width: 68ch; }
  p.callout { padding: 8px 10px; border-radius: var(--radius-sm); background: var(--surface-subtle); }
  .var { padding: 0 5px; border-radius: 5px; background: var(--info-bg); color: var(--info-text); font-size: 12px; }
  .answer { display: grid; gap: 2px; }
  .mini-table { display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); border-radius: var(--radius-sm); overflow: hidden; }
  .mini-table span { padding: 5px 8px; background: var(--surface-subtle); font-size: 12px; font-weight: 600; }
  .caption { font-size: 12px; color: var(--text-muted); }
  .break { display: flex; align-items: center; gap: 10px; color: var(--text-muted); font-size: 12px; }
  .break::before, .break::after { content: ""; flex: 1; border-top: 1px dashed var(--border-strong); }
  .sigs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .sig { display: grid; place-items: center; height: 46px; border: 1px dashed var(--border-strong); border-radius: var(--radius-sm); font-size: 12px; color: var(--text-muted); }
  .sig.hand { font-family: var(--font-sign); font-size: 20px; color: var(--text); }
  .sig.stamp { border: 2px solid var(--fjord); color: var(--link); font-weight: 600; letter-spacing: 0.08em; font-size: 10.5px; text-transform: uppercase; }
  .props { position: sticky; top: 12px; }
  .note { margin: 0; color: var(--text-muted); font-size: 13px; }
  @media (max-width: 1180px) { .workspace { grid-template-columns: 220px minmax(0, 1fr); } .props { grid-column: 1 / -1; position: static; } }
  @media (max-width: 860px) { .workspace { grid-template-columns: minmax(0, 1fr); } .block.inside { margin-left: 8px; } }
</style>
