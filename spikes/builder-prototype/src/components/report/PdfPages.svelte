<script>
  // The report as A4 pages, laid out by the same rules the PDF renderer uses.
  import Mark from '../Mark.svelte'
  import {context, templateAssets, SIGNER_ROLES} from '../../lib/sample.js'
  import {buildPages, interpolate, formatValue, maskSecret} from '../../lib/pages.js'
  import {calloutColours} from '../../lib/colour.js'
  import {doc, templateData, ruleResult} from '../../lib/state.svelte.js'

  let {answers, onpages = () => {}} = $props()

  const data = $derived(templateData(answers))
  const isShown = (rule) => {
    const r = ruleResult(rule, data)
    return {shown: r.ok ? r.value !== false : true, error: r.ok ? null : r.error}
  }
  const layout = $derived(buildPages(doc.blocks, isShown))
  const total = $derived(layout.pages.length)
  $effect(() => onpages({total, hidden: layout.hidden.length}))

  const question = (key) => doc.questions.find((q) => q.key === key)
  const rowsOf = (key) => (Array.isArray(data.answers[key]) ? data.answers[key] : [])
  const parts = (text) => interpolate(text, data, doc.questions)
  const plain = (text) => parts(text).map((p) => p.text).join('')
  const signedAt = new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'short', year: 'numeric'}).format(new Date('2026-10-22T10:00'))
  const signerName = (role) => (role === 'technician' ? context.report.technician : role === 'reviewer' ? context.report.reviewer : context.company.name)

  function answerText(q, value) {
    if (q?.type === 'secret') return maskSecret(value, q.secret) || '—'
    return formatValue(value, q?.type)
  }
  function columnsOf(block, q) {
    const all = q?.columns ?? []
    if (!block.columns) return all
    return block.columns.map((k) => all.find((c) => c.key === k)).filter(Boolean)
  }
  function imageSrc(block) {
    if (block.source === 'template') return templateAssets[block.asset]?.src ?? ''
    const value = data.answers[block.question]
    return typeof value === 'string' && value.startsWith('data:image/') ? value : ''
  }

  // Flags a page whose content is taller than A4; the PDF renderer would flow it onto another page.
  let overflowing = $state({})
  function overflow(node, index) {
    const check = () => {
      const a4 = getComputedStyle(node).aspectRatio !== 'auto'
      const over = a4 && node.offsetHeight > (node.offsetWidth * 297) / 210 + 2
      if (overflowing[index] !== over) overflowing[index] = over
    }
    const observer = new ResizeObserver(check)
    observer.observe(node)
    return {update: (i) => (index = i), destroy: () => observer.disconnect()}
  }
</script>

<div class="pages">
  {#each layout.pages as page, p (p)}
    <div class="page-wrap">
      <div class="page-label"><span class="overline">Page {p + 1} of {total}</span><span class="reason">{page.reason}</span></div>
      <article class="sheet" class:over={overflowing[p]} use:overflow={p} aria-label="PDF page {p + 1} of {total}">
        <header class="run-head">
          <span class="brand"><Mark size={18} />{context.company.name}</span>
          <span class="ref"><span class="mono">{context.report.number}</span><span class="tlp">{context.report.classification}</span></span>
        </header>

        <div class="content">
          {#if page.cover}
            <div class="cover">
              <span class="kicker">Security incident report</span>
              <h1>{context.project.name}</h1>
              <p class="for">Prepared for {context.customer.name}</p>
              <dl class="facts">
                {#each doc.coverFacts as fact (fact.label)}
                  <div><dt>{fact.label}</dt><dd class:mono={fact.mono}>{#each parts(fact.text) as part, i (i)}{#if part.missing}<span class="missing">{part.text}</span>{:else}{part.text}{/if}{/each}</dd></div>
                {/each}
              </dl>
            </div>
          {/if}

          {#each page.items as item (item.block.id)}
            {@const block = item.block}
            <div class="item" class:rule-error={item.rule.error}>
              {#if item.rule.error}<span class="pill critical wrap">Rule error: {item.rule.error}</span>{/if}
              {#if block.kind === 'section'}
                <h2 class="section">{#if item.number}<span class="num">{item.number}</span>{/if}{plain(block.title)}</h2>
                {#if block.intro}<p class="intro">{plain(block.intro)}</p>{/if}
              {:else if block.kind === 'heading'}
                <h3>{plain(block.text)}</h3>
              {:else if block.kind === 'text'}
                <p>{#each parts(block.text) as part, i (i)}{#if part.missing}<span class="missing">{part.text}</span>{:else if part.secret}<span class="secret">{part.text}</span>{:else}{part.text}{/if}{/each}</p>
              {:else if block.kind === 'callout'}
                {@const c = calloutColours(block)}
                <div class="callout" style="--c-bg: {c.bg}; --c-fg: {c.fg}; --c-border: {c.border}">
                  {#if block.title}<strong>{plain(block.title)}</strong>{/if}
                  <p>{#each parts(block.text) as part, i (i)}{#if part.missing}<span class="missing">{part.text}</span>{:else}{part.text}{/if}{/each}</p>
                </div>
              {:else if block.kind === 'answer'}
                {@const q = question(block.question)}
                <div class="answer">
                  {#if block.showLabel}<span class="answer-label">{q?.label ?? 'Removed question'}</span>{/if}
                  {#if q?.type === 'photo'}
                    {#if imageSrc({source: 'question', question: block.question})}<img class="photo" src={imageSrc({source: 'question', question: block.question})} alt={q.label} />{:else}<p class="empty">No photo</p>{/if}
                  {:else}
                    <p class:secret={q?.type === 'secret'}>{answerText(q, data.answers[block.question])}</p>
                  {/if}
                </div>
              {:else if block.kind === 'table'}
                {@const q = question(block.question)}
                {@const cols = columnsOf(block, q)}
                <figure class="table-fig">
                  {#if block.caption}<figcaption class="caption"><strong>Table {item.caption}.</strong> {plain(block.caption)}</figcaption>{/if}
                  {#if cols.length}
                    <table>
                      <thead><tr>{#each cols as c (c.key)}<th scope="col" class:num-col={c.type === 'number'}>{c.label}</th>{/each}</tr></thead>
                      <tbody>
                        {#each rowsOf(block.question) as row, i (i)}
                          <tr>{#each cols as c (c.key)}<td class:mono={c.type === 'ip'} class:num-col={c.type === 'number'}>{formatValue(row[c.key], c.type)}</td>{/each}</tr>
                        {:else}
                          <tr><td colspan={cols.length} class="empty">{block.emptyText || 'No rows.'}</td></tr>
                        {/each}
                      </tbody>
                    </table>
                  {/if}
                </figure>
              {:else if block.kind === 'image'}
                {@const src = imageSrc(block)}
                <figure class="image-fig {block.width}">
                  {#if src}<img src={src} alt={plain(block.caption) || 'Image'} />{:else}<div class="no-image">No image yet</div>{/if}
                  {#if block.caption}<figcaption class="caption"><strong>Figure {item.caption}.</strong> {plain(block.caption)}</figcaption>{/if}
                </figure>
              {:else if block.kind === 'sources'}
                {@const all = [...(block.items ?? []), ...(block.question ? rowsOf(block.question) : [])]}
                {#if block.intro}<p class="intro">{plain(block.intro)}</p>{/if}
                <ol class="sources">
                  {#each all as s, i (i)}
                    <li><span class="src-n mono">[{i + 1}]</span><span class="src-body"><span>{s.title || 'Untitled source'}</span>{#if s.link}<span class="src-link mono">{s.link}</span>{/if}</span></li>
                  {:else}
                    <li class="empty">No sources listed.</li>
                  {/each}
                </ol>
              {:else if block.kind === 'signatures'}
                <div class="sigs {block.layout}" style="--n: {block.signers.length}">
                  {#each block.signers as s, i (i)}
                    <figure class="sig">
                      {#if s.style === 'stamp'}
                        <span class="stamp"><Mark size={22} /><span><strong>{signerName(s.role)}</strong>Digitally signed</span></span>
                      {:else}
                        <span class="hand">{signerName(s.role)}</span>
                      {/if}
                      <figcaption><strong>{s.label || SIGNER_ROLES[s.role]}</strong>{signerName(s.role)}{#if block.showDate} · signed {signedAt}{/if}</figcaption>
                    </figure>
                  {/each}
                </div>
                <p class="sig-note">Sample signatures. In the PDF each one is a digital signature that can be checked.</p>
              {/if}
            </div>
          {/each}
        </div>

        <footer class="run-foot">
          <span>{context.customer.name} · {context.report.classification}</span>
          <span>Page {p + 1} of {total}</span>
        </footer>
      </article>
      {#if overflowing[p]}<p class="overflow-note">This page is longer than A4. The PDF flows the rest onto the next page.</p>{/if}
    </div>
  {/each}
</div>

<style>
  .pages { display: grid; grid-template-columns: minmax(0, 1fr); gap: 22px; justify-items: center; min-width: 0; }
  .page-wrap { width: 100%; max-width: 640px; display: grid; gap: 6px; }
  .page-label { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
  .reason { font-size: 12px; color: var(--text-muted); }

  /* The sheet: A4 proportions, paper colours in both themes, type scaled with the page width.
     min-width: 0 stops a tall page from widening itself through its aspect ratio; it grows taller instead. */
  .sheet { container-type: inline-size; width: 100%; min-width: 0; aspect-ratio: 210 / 297; display: flex; flex-direction: column;
    background: var(--paper); color: var(--paper-ink); border: 1px solid var(--border); border-radius: 4px;
    padding: 6cqi 8cqi 5cqi; font-size: clamp(8px, 1.75cqi, 12px); line-height: 1.5; --mark-frame: transparent; }
  .sheet.over { outline: 2px solid var(--warning-text); outline-offset: 3px; }
  .overflow-note { margin: 0; font-size: 12px; color: var(--warning-text); }
  .run-head, .run-foot { display: flex; justify-content: space-between; gap: 2cqi; align-items: center; font-size: 0.82em; color: var(--paper-muted); }
  .run-head { padding-bottom: 2cqi; border-bottom: 1px solid var(--paper-line); }
  .run-foot { padding-top: 2cqi; border-top: 1px solid var(--paper-line); margin-top: 3cqi; }
  .brand { display: inline-flex; align-items: center; gap: 1.4cqi; font-weight: 600; color: var(--paper-ink); }
  .ref { display: inline-flex; align-items: center; gap: 1.6cqi; }
  .ref .mono { font-size: 1em; }
  .tlp { padding: 0.1em 0.6em; border-radius: 3px; background: var(--tlp-amber-bg); color: var(--tlp-amber-text); font-family: var(--font-mono); font-weight: 500; letter-spacing: 0.04em; }
  .content { flex: 1; display: grid; align-content: start; gap: 2.4cqi; padding-top: 4cqi; }

  .cover { display: grid; gap: 1.6cqi; padding-bottom: 4cqi; margin-bottom: 1cqi; border-bottom: 1px solid var(--paper-line); }
  .kicker { font-size: 0.86em; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--fjord); }
  .cover h1 { font-size: 2.6em; line-height: 1.1; color: var(--paper-ink); }
  .for { margin: 0; font-size: 1.15em; color: var(--paper-muted); }
  .facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 4cqi; margin: 2cqi 0 0; }
  .facts div { display: grid; grid-template-columns: 6.2em minmax(0, 1fr); gap: 1cqi; padding: 0.9cqi 0; border-bottom: 1px solid var(--paper-line); }
  .facts dt { color: var(--paper-muted); }
  .facts dd { margin: 0; font-weight: 500; }
  .facts .mono { font-size: 1em; }

  .item { display: grid; gap: 1cqi; min-width: 0; }
  .item.rule-error { outline: 1px dashed var(--paper-critical-text); outline-offset: 4px; }
  h2.section { display: flex; gap: 2cqi; align-items: baseline; font-size: 1.75em; color: var(--paper-ink); padding-bottom: 1cqi; border-bottom: 2px solid var(--paper-ink); }
  .num { font-family: var(--font-mono); font-size: 0.6em; color: var(--fjord); }
  .intro { color: var(--paper-muted); }
  h3 { margin: 1cqi 0 0; font-family: var(--font-display); font-weight: 400; font-size: 1.25em; color: var(--paper-ink); }
  .item p { margin: 0; max-width: 68ch; }
  .callout { display: grid; gap: 0.6cqi; padding: 2cqi 2.6cqi; border: 1px solid var(--c-border); border-radius: 6px; background: var(--c-bg); color: var(--c-fg); }
  .callout strong { font-weight: 600; }
  .answer { display: grid; gap: 0.6cqi; }
  .answer-label { font-size: 0.86em; font-weight: 600; color: var(--paper-muted); }
  .missing { padding: 0 0.3em; border-radius: 3px; background: var(--paper-critical-bg); color: var(--paper-critical-text); font-family: var(--font-mono); font-size: 0.9em; }
  .secret { font-family: var(--font-mono); letter-spacing: 0.04em; }
  figure { margin: 0; display: grid; gap: 1cqi; }
  .caption { font-size: 0.9em; color: var(--paper-muted); }
  .caption strong { color: var(--paper-ink); font-weight: 600; }
  table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  th { text-align: left; font-weight: 600; font-size: 0.9em; padding: 1cqi 1.4cqi; background: var(--paper-subtle); border-bottom: 1px solid var(--paper-muted); }
  td { padding: 1cqi 1.4cqi; border-bottom: 1px solid var(--paper-line); }
  td.mono { font-size: 0.95em; }
  .num-col { text-align: right; }
  .empty { color: var(--paper-muted); font-style: italic; }
  /* Images never take more than about 40% of a page's height, whatever their shape. */
  .image-fig img, .photo { width: 100%; height: auto; max-height: 58cqi; object-fit: contain; border: 1px solid var(--paper-line); border-radius: 4px; background: var(--paper); }
  .image-fig.half { width: 50%; }
  .image-fig.third { width: 34%; }
  .no-image { display: grid; place-items: center; min-height: 14cqi; border: 1px dashed var(--paper-muted); border-radius: 4px; color: var(--paper-muted); }
  .sources { list-style: none; margin: 0; padding: 0; display: grid; gap: 1cqi; }
  .sources li { display: grid; grid-template-columns: 2.6em minmax(0, 1fr); gap: 1cqi; }
  .src-n { color: var(--fjord); font-size: 0.95em; }
  .src-body { display: grid; min-width: 0; }
  .src-link { font-size: 0.85em; color: var(--paper-muted); overflow-wrap: anywhere; }
  .sigs { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 2.4cqi; margin-top: 2cqi; }
  .sigs.stacked { grid-template-columns: minmax(0, 0.5fr); }
  .sig { margin: 0; display: grid; gap: 1cqi; align-content: start; }
  .hand, .stamp { height: 11cqi; display: flex; align-items: center; }
  .hand { font-family: var(--font-sign); font-size: 2.2em; color: var(--sign-ink); padding-left: 1cqi; border-bottom: 1px solid var(--paper-ink); overflow: hidden; white-space: nowrap; }
  .stamp { gap: 1.4cqi; padding: 0 1.6cqi; border: 2px solid var(--fjord); border-radius: 6px; color: var(--fjord); font-size: 0.82em; line-height: 1.25;
    box-shadow: inset 0 0 0 2px var(--paper), inset 0 0 0 3px var(--fjord); }
  .stamp span { display: grid; }
  .stamp strong { letter-spacing: 0.02em; }
  .sig figcaption { display: grid; font-size: 0.82em; color: var(--paper-muted); }
  .sig figcaption strong { color: var(--paper-ink); font-weight: 600; }
  .sig-note { font-size: 0.82em; color: var(--paper-muted); }

  @media (max-width: 860px) {
    .sheet { aspect-ratio: auto; min-height: 0; }
    .facts { grid-template-columns: minmax(0, 1fr); }
    .sigs, .sigs.stacked { grid-template-columns: minmax(0, 1fr); }
    .hand, .stamp { height: 52px; }
    .image-fig.half, .image-fig.third { width: 100%; }
  }
</style>
