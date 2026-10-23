<script>
  import AnswerForm from './AnswerForm.svelte'
  import Mark from './Mark.svelte'
  import {context} from '../lib/sample.js'
  import {describeRule} from '../lib/cel.js'
  import {buildPages, interpolate, formatValue} from '../lib/pages.js'
  import {doc, templateData, ruleResult} from '../lib/state.svelte.js'

  const data = $derived(templateData(doc.answers))
  const isShown = (rule) => {
    const r = ruleResult(rule, data)
    return {shown: r.ok ? r.value !== false : true, error: r.ok ? null : r.error}
  }
  const layout = $derived(buildPages(doc.blocks, isShown))
  const total = $derived(layout.pages.length)

  const rules = $derived([
    ...doc.questions.filter((q) => q.showWhen).map((q) => ({where: `Question “${q.label}”`, rule: q.showWhen})),
    ...doc.blocks.filter((b) => b.showWhen).map((b) => ({where: b.kind === 'section' ? `Section “${b.title}”` : `${b.kind[0].toUpperCase()}${b.kind.slice(1)} block`, rule: b.showWhen})),
  ].map((r) => ({...r, result: ruleResult(r.rule, data)})))

  const question = (key) => doc.questions.find((q) => q.key === key)
  const rowsOf = (key) => (Array.isArray(data.answers[key]) ? data.answers[key] : [])
  const signedAt = new Intl.DateTimeFormat('en-GB', {day: 'numeric', month: 'short', year: 'numeric'}).format(new Date('2026-10-22T10:00'))

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
    for (const child of node.children) observer.observe(child)
    return {update: (i) => (index = i), destroy: () => observer.disconnect()}
  }
</script>

<div class="preview">
  <AnswerForm />

  <section class="pages" aria-label="Report preview">
    <div class="pages-head">
      <div>
        <h2>{total} pages</h2>
        <p>Pages break where the PDF breaks: sections set to start on a new page, and page-break blocks. Table rows never split across pages.</p>
      </div>
      {#if layout.hidden.length}<span class="pill plain">{layout.hidden.length} block{layout.hidden.length === 1 ? '' : 's'} hidden by rules</span>{/if}
    </div>

    {#each layout.pages as page, p (p)}
      <div class="page-wrap">
        <div class="page-label"><span class="overline">Page {p + 1} of {total}</span><span class="reason">{page.reason}</span></div>
        <article class="sheet" class:over={overflowing[p]} use:overflow={p} aria-label="Page {p + 1} of {total}">
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
                    <div><dt>{fact.label}</dt><dd class:mono={fact.mono}>{#each interpolate(fact.text, data, doc.questions) as part, i (i)}{#if part.missing}<span class="missing">{part.text}</span>{:else}{part.text}{/if}{/each}</dd></div>
                  {/each}
                </dl>
              </div>
            {/if}

            {#each page.items as {block, number, rule} (block.id)}
              <div class="item" class:rule-error={rule.error}>
                {#if rule.error}<span class="pill critical">Rule error: {rule.error}</span>{/if}
                {#if block.kind === 'section'}
                  <h2 class="section"><span class="num">{number}</span>{block.title}</h2>
                {:else if block.kind === 'heading'}
                  <h3>{block.title ?? block.text}</h3>
                {:else if block.kind === 'text' || block.kind === 'callout'}
                  <p class:callout={block.kind === 'callout'}>
                    {#each interpolate(block.text, data, doc.questions) as part, i (i)}{#if part.missing}<span class="missing">{part.text}</span>{:else if part.secret}<span class="secret">{part.text}</span>{:else}{part.text}{/if}{/each}
                  </p>
                {:else if block.kind === 'answer'}
                  {@const q = question(block.question)}
                  <div class="answer">
                    <span class="answer-label">{q?.label ?? 'Removed question'}</span>
                    <p>{formatValue(data.answers[block.question], q?.type)}</p>
                  </div>
                {:else if block.kind === 'table'}
                  {@const q = question(block.question)}
                  {#if q?.columns}
                    <table>
                      <thead><tr>{#each q.columns as c (c.key)}<th scope="col" class:num-col={c.type === 'number'}>{c.label}</th>{/each}</tr></thead>
                      <tbody>
                        {#each rowsOf(block.question) as row, i (i)}
                          <tr>{#each q.columns as c (c.key)}<td class:mono={c.type === 'ip'} class:num-col={c.type === 'number'}>{formatValue(row[c.key], c.type)}</td>{/each}</tr>
                        {:else}
                          <tr><td colspan={q.columns.length} class="empty">No rows</td></tr>
                        {/each}
                      </tbody>
                    </table>
                  {/if}
                {:else if block.kind === 'signatures'}
                  <div class="sigs">
                    <figure class="sig">
                      <span class="hand">{context.report.technician}</span>
                      <figcaption><strong>{context.report.technician}</strong>Technician · signed {signedAt}</figcaption>
                    </figure>
                    <figure class="sig">
                      <span class="hand">{context.report.reviewer}</span>
                      <figcaption><strong>{context.report.reviewer}</strong>Reviewer · signed {signedAt}</figcaption>
                    </figure>
                    <figure class="sig">
                      <span class="stamp"><Mark size={22} /><span><strong>{context.company.name}</strong>Digitally sealed</span></span>
                      <figcaption><strong>Company seal</strong>PAdES · timestamped</figcaption>
                    </figure>
                  </div>
                  <p class="sig-note">Sample appearances. In the PDF each one is a digital signature that can be checked.</p>
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
  </section>

  <aside class="panel rules" aria-label="Rules">
    <div class="panel-head"><h2>Rules</h2></div>
    <div class="panel-body">
      {#each rules as r, i (i)}
        <div class="rule">
          <span class="where">{r.where}</span>
          <span class="desc">Only when {describeRule(r.rule, doc.questions)}</span>
          <code class="mono">{r.result.expr}</code>
          {#if !r.result.ok}<span class="pill critical">Error: {r.result.error}</span>
          {:else}<span class="pill {r.result.value ? 'ok' : 'plain'}">{r.result.value ? 'True: shown' : 'False: hidden'}</span>{/if}
        </div>
      {:else}
        <p class="note">No rules yet.</p>
      {/each}
    </div>
  </aside>
</div>

<style>
  .preview { display: grid; grid-template-columns: 300px minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
  .pages { min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 22px; justify-items: center; }
  .pages-head { width: 100%; max-width: 640px; display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: flex-start; justify-content: space-between; }
  .pages-head h2 { font-size: 22px; }
  .pages-head p { margin: 2px 0 0; color: var(--text-muted); font-size: 13px; max-width: 60ch; }
  .page-wrap { width: 100%; max-width: 640px; display: grid; gap: 6px; }
  .page-label { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
  .reason { font-size: 12px; color: var(--text-muted); }

  /* The sheet: A4 proportions, paper colours in both themes, type scaled with the page width. */
  /* min-width: 0 stops a tall page from widening itself through its aspect ratio; it grows taller instead. */
  .sheet { container-type: inline-size; width: 100%; min-width: 0; aspect-ratio: 210 / 297; display: flex; flex-direction: column;
    background: var(--paper); color: var(--paper-ink); border: 1px solid var(--border); border-radius: 4px;
    padding: 6cqi 8cqi 5cqi; font-size: clamp(8px, 1.75cqi, 12px); line-height: 1.5; }
  .sheet { --mark-frame: transparent; }
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
  .item.rule-error { outline: 1px dashed var(--critical-text); outline-offset: 4px; }
  h2.section { display: flex; gap: 2cqi; align-items: baseline; font-size: 1.75em; color: var(--paper-ink); padding-bottom: 1cqi; border-bottom: 2px solid var(--paper-ink); }
  .num { font-family: var(--font-mono); font-size: 0.6em; color: var(--fjord); }
  h3 { margin: 1cqi 0 0; font-family: var(--font-display); font-weight: 400; font-size: 1.25em; color: var(--paper-ink); }
  .item p { margin: 0; max-width: 68ch; }
  p.callout { padding: 2cqi 2.6cqi; border: 1px solid var(--paper-line); border-radius: 6px; background: var(--paper-subtle); font-weight: 500; }
  .answer-label { font-size: 0.86em; font-weight: 600; color: var(--paper-muted); }
  .missing { padding: 0 0.3em; border-radius: 3px; background: var(--paper-critical-bg); color: var(--paper-critical-text); font-family: var(--font-mono); font-size: 0.9em; }
  .secret { font-family: var(--font-mono); letter-spacing: 0.1em; }
  table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  th { text-align: left; font-weight: 600; font-size: 0.9em; padding: 1cqi 1.4cqi; background: var(--paper-subtle); border-bottom: 1px solid var(--paper-muted); }
  td { padding: 1cqi 1.4cqi; border-bottom: 1px solid var(--paper-line); }
  td.mono { font-size: 0.95em; }
  .num-col { text-align: right; }
  .empty { color: var(--paper-muted); font-style: italic; }
  .sigs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 2.4cqi; margin-top: 2cqi; }
  .sig { margin: 0; display: grid; gap: 1cqi; }
  .hand, .stamp { height: 11cqi; display: flex; align-items: center; border-bottom: 1px solid var(--paper-ink); }
  .hand { font-family: var(--font-sign); font-size: 2.2em; color: var(--sign-ink); padding-left: 1cqi; }
  .stamp { gap: 1.4cqi; padding: 0 1.6cqi; border: 2px solid var(--fjord); border-radius: 6px; color: var(--fjord); font-size: 0.82em; line-height: 1.25;
    box-shadow: inset 0 0 0 2px var(--paper), inset 0 0 0 3px var(--fjord); }
  .stamp span { display: grid; }
  .stamp strong { letter-spacing: 0.02em; }
  figcaption { display: grid; font-size: 0.82em; color: var(--paper-muted); }
  figcaption strong { color: var(--paper-ink); font-weight: 600; }
  .sig-note { font-size: 0.82em; color: var(--paper-muted); }

  .rules { position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto; }
  .rule { display: grid; gap: 4px; justify-items: start; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
  .rule:last-child { border-bottom: 0; padding-bottom: 0; }
  .where { font-weight: 600; font-size: 13px; }
  .desc { font-size: 12.5px; color: var(--text-muted); }
  .rule code { max-width: 100%; overflow-x: auto; white-space: pre; font-size: 12px; }
  .note { margin: 0; color: var(--text-muted); font-size: 13px; }

  @media (max-width: 1180px) {
    .preview { grid-template-columns: 300px minmax(0, 1fr); }
    .rules { grid-column: 1 / -1; position: static; max-height: none; }
  }
  @media (max-width: 860px) {
    .preview { grid-template-columns: minmax(0, 1fr); }
    .sheet { aspect-ratio: auto; min-height: 0; }
    .facts { grid-template-columns: minmax(0, 1fr); }
    .sigs { grid-template-columns: minmax(0, 1fr); }
    .hand, .stamp { height: 52px; }
  }
</style>
