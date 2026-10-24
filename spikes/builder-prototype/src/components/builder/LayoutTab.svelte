<script>
  import {dndzone} from 'svelte-dnd-action'
  import Palette from '../Palette.svelte'
  import Where from '../Where.svelte'
  import BlockSettings from './BlockSettings.svelte'
  import {BLOCK_TYPES, SIGNER_ROLES, newBlock, context, templateAssets} from '../../lib/sample.js'
  import {describeRule} from '../../lib/cel.js'
  import {calloutColours} from '../../lib/colour.js'
  import {doc} from '../../lib/state.svelte.js'

  const paletteEntries = Object.entries(BLOCK_TYPES).map(([kind, t]) => ({id: `pal-${kind}`, kind, label: t.label, hint: t.hint, glyph: t.glyph}))
  const selected = $derived(doc.blocks.find((b) => b.id === doc.selectedBlock))

  // Section number for each block, so the canvas shows the report's structure.
  const sectionOf = $derived.by(() => {
    const map = {}
    let n = 0
    for (const b of doc.blocks) {
      if (b.kind === 'section' && b.numbered !== false) n += 1
      map[b.id] = n
    }
    return map
  })

  function consider(e) {
    doc.blocks = e.detail.items
  }
  function finalize(e) {
    let fresh = null
    doc.blocks = e.detail.items.map((item) => (item.palette ? (fresh = newBlock(item.kind)) : item))
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
  const questionLabel = (key) => doc.questions.find((q) => q.key === key)?.label ?? 'Choose a question'
  const columnsOf = (b) => {
    const all = doc.questions.find((q) => q.key === b.question)?.columns ?? []
    return b.columns ? b.columns.map((k) => all.find((c) => c.key === k)).filter(Boolean) : all
  }
  const parts = (text) => String(text ?? '').split(/(\{\{\s*[\w.]+\s*\}\})/g)
</script>

<div class="workspace">
  <Palette entries={paletteEntries} type="blocks" title="Blocks" onadd={addAfterSelected} />

  <section class="canvas" aria-label="PDF layout">
    <div class="intro">
      <div class="intro-title"><h2>The PDF</h2><Where pdf /></div>
      <p>What the customer receives, block by block, in this order. Blocks print answers from the form, library text and calculated values. A rule can leave a block or a whole section out.</p>
    </div>
    <div class="paper">
      <div class="cover" aria-hidden="true">
        <span class="overline">Cover page · filled in automatically</span>
        <span class="cover-title">{context.project.name}</span>
        <span class="cover-meta">{context.customer.name} · {context.report.number} · key facts</span>
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
                <span class="overline">{block.numbered !== false ? `Section ${sectionOf[block.id]}` : 'Section, not numbered'}</span>
                <h3>{block.title}</h3>
                {#if block.intro}<p class="muted">{block.intro}</p>{/if}
              </div>
              <div class="chips">
                <span class="pill {block.newPage ? 'info' : 'plain'}">{block.newPage ? 'Starts a new page' : 'Continues on the same page'}</span>
                {#if block.showWhen}<span class="pill warning wrap">Only when {describeRule(block.showWhen, doc.questions)}</span>{/if}
              </div>
            {:else if block.kind === 'heading'}
              <h4>{block.text}</h4>
            {:else if block.kind === 'text'}
              <p>{#each parts(block.text) as part, i (i)}{#if part.startsWith('{{')}<span class="var mono">{part.replace(/[{}\s]/g, '')}</span>{:else}{part}{/if}{/each}</p>
            {:else if block.kind === 'callout'}
              {@const c = calloutColours(block)}
              <div class="callout" style="--c-bg: {c.bg}; --c-fg: {c.fg}; --c-border: {c.border}">
                {#if block.title}<strong>{#each parts(block.title) as part, i (i)}{#if part.startsWith('{{')}<span class="var mono">{part.replace(/[{}\s]/g, '')}</span>{:else}{part}{/if}{/each}</strong>{/if}
                <span>{#each parts(block.text) as part, i (i)}{#if part.startsWith('{{')}<span class="var mono">{part.replace(/[{}\s]/g, '')}</span>{:else}{part}{/if}{/each}</span>
              </div>
            {:else if block.kind === 'answer'}
              <div class="answer"><span class="overline">Answer</span><span>{questionLabel(block.question)}</span></div>
            {:else if block.kind === 'table'}
              {#if block.caption}<span class="caption">Table · {block.caption}</span>{/if}
              <div class="mini-table" style="--cols: {columnsOf(block).length || 1}">
                {#each columnsOf(block) as c (c.key)}<span>{c.label}</span>{/each}
              </div>
              <span class="caption">One row per entry in “{questionLabel(block.question)}”</span>
            {:else if block.kind === 'image'}
              <div class="image">
                {#if block.source === 'template'}<img src={templateAssets[block.asset]?.src} alt="" />{:else}<span class="ph">Photo: {questionLabel(block.question)}</span>{/if}
                <span class="caption">{block.caption ? `Figure · ${block.caption}` : 'No caption'} · {block.width === 'full' ? 'full width' : block.width === 'half' ? 'half width' : 'a third'}</span>
              </div>
            {:else if block.kind === 'sources'}
              <span class="caption">{block.items.length} fixed source{block.items.length === 1 ? '' : 's'}{block.question ? `, plus the technician's from “${questionLabel(block.question)}”` : ''}</span>
            {:else if block.kind === 'pagebreak'}
              <div class="break"><span>Page break</span></div>
            {:else if block.kind === 'signatures'}
              <div class="sigs" style="--n: {block.layout === 'row' ? block.signers.length : 1}">
                {#each block.signers as s, i (i)}<span class="sig" class:stamp={s.style === 'stamp'} class:hand={s.style !== 'stamp'}>{s.label || SIGNER_ROLES[s.role]}</span>{/each}
              </div>
            {/if}
            {#if block.kind !== 'section' && block.showWhen}
              <span class="pill warning wrap when">Only when {describeRule(block.showWhen, doc.questions)}</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  </section>

  <aside class="panel props" aria-label="Block settings">
    {#if selected}
      <BlockSettings block={selected} />
    {:else}
      <div class="panel-body"><p class="note">Select a block on the page to change it.</p></div>
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
  .paper { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 24px clamp(16px, 4vw, 40px) 32px; }
  .cover { display: grid; gap: 4px; padding: 14px 16px; margin-bottom: 16px; border-radius: var(--radius-md); background: var(--surface-subtle); }
  .cover-title { font-family: var(--font-display); font-size: 22px; }
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
  .muted { color: var(--text-muted); font-size: 13px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .when { justify-self: start; }
  h4 { margin: 0; font-family: var(--font-display); font-weight: 400; font-size: 16px; }
  p { margin: 0; max-width: 68ch; }
  .callout { display: grid; gap: 2px; padding: 8px 10px; border-radius: var(--radius-sm); border: 1px solid var(--c-border); background: var(--c-bg); color: var(--c-fg); }
  .var { padding: 0 5px; border-radius: 5px; background: var(--info-bg); color: var(--info-text); font-size: 12px; }
  .callout .var { background: color-mix(in srgb, currentColor 14%, transparent); color: inherit; }
  .answer { display: grid; gap: 2px; }
  .mini-table { display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); border-radius: var(--radius-sm); overflow: hidden; }
  .mini-table span { padding: 5px 8px; background: var(--surface-subtle); font-size: 12px; font-weight: 600; }
  .caption { font-size: 12px; color: var(--text-muted); }
  .image { display: grid; gap: 4px; }
  .image img { max-height: 90px; width: auto; max-width: 100%; justify-self: start; border-radius: var(--radius-sm); border: 1px solid var(--border); background: #FFFFFF; }
  .ph { display: grid; place-items: center; height: 70px; border: 1px dashed var(--border-strong); border-radius: var(--radius-sm); font-size: 12px; color: var(--text-muted); }
  .break { display: flex; align-items: center; gap: 10px; color: var(--text-muted); font-size: 12px; }
  .break::before, .break::after { content: ""; flex: 1; border-top: 1px dashed var(--border-strong); }
  .sigs { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 8px; }
  .sig { display: grid; place-items: center; height: 46px; border: 1px dashed var(--border-strong); border-radius: var(--radius-sm); font-size: 12px; color: var(--text-muted); text-align: center; }
  .sig.hand { font-family: var(--font-sign); font-size: 20px; color: var(--text); }
  .sig.stamp { border: 2px solid var(--fjord); color: var(--link); font-weight: 600; font-size: 11px; }
  .props { position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto; }
  .note { margin: 0; color: var(--text-muted); font-size: 13px; }
  @media (max-width: 1180px) { .workspace { grid-template-columns: 220px minmax(0, 1fr); } .props { grid-column: 1 / -1; position: static; max-height: none; } }
  @media (max-width: 860px) { .workspace { grid-template-columns: minmax(0, 1fr); } .block.inside { margin-left: 8px; } .sigs { grid-template-columns: minmax(0, 1fr); } }
</style>
