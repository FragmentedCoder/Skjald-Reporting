<script>
  // The template builder: only administrators and report designers get here.
  import QuestionsTab from './QuestionsTab.svelte'
  import LayoutTab from './LayoutTab.svelte'
  import DataTab from './DataTab.svelte'
  import ReportView from '../report/ReportView.svelte'
  import Where from '../Where.svelte'
  import {session} from '../../lib/state.svelte.js'

  let {onselect} = $props()

  const TABS = [
    {id: 'questions', label: 'Questions', sub: 'The form'},
    {id: 'layout', label: 'Layout', sub: 'The PDF'},
    {id: 'data', label: 'Data', sub: 'Names and functions'},
    {id: 'try', label: 'Try it', sub: 'As a technician'},
  ]

  function onkeydown(e) {
    const i = TABS.findIndex((t) => t.id === session.view)
    const next = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? TABS.length - 1 : null
    if (next === null) return
    e.preventDefault()
    const tab = TABS[(next + TABS.length) % TABS.length]
    onselect(tab.id)
    document.getElementById(`tab-${tab.id}`)?.focus()
  }
  function publish() {
    session.notice = 'Prototype: nothing is saved. In Skjald, publishing makes version 4 the one new reports use; reports already started stay on version 3.'
  }
</script>

<div class="builder">
  <header class="head">
    <div class="titles">
      <nav class="crumbs" aria-label="Breadcrumb"><span>Templates</span><span aria-hidden="true">›</span><span aria-current="page">Security incident report</span></nav>
      <div class="title-row"><h1>Security incident report</h1><span class="pill info">Draft of version 4</span></div>
    </div>
    <button type="button" class="btn accent" onclick={publish}>Publish version 4</button>
  </header>

  <div class="legend">
    <p><strong>You're editing the template.</strong> Technicians never see this screen: they fill in the form from the Questions tab, and the customer receives the PDF from the Layout tab.</p>
    <dl>
      <div><dt><Where form compact /></dt><dd>The technician sees it while filling in a report</dd></div>
      <div><dt><Where pdf compact /></dt><dd>Printed in the PDF for the customer</dd></div>
      <div><dt><Where builder compact /></dt><dd>Only you and other builders see it</dd></div>
    </dl>
  </div>

  <div class="tabs" role="tablist" aria-label="Template builder" tabindex="-1" {onkeydown}>
    {#each TABS as t (t.id)}
      <button type="button" role="tab" id="tab-{t.id}" aria-selected={session.view === t.id} aria-controls="builder-panel" tabindex={session.view === t.id ? 0 : -1}
        class:active={session.view === t.id} onclick={() => onselect(t.id)}><span class="t">{t.label}</span><span class="s">{t.sub}</span></button>
    {/each}
  </div>

  <div id="builder-panel" role="tabpanel" aria-labelledby="tab-{session.view}">
    {#if session.view === 'questions'}<QuestionsTab />
    {:else if session.view === 'layout'}<LayoutTab />
    {:else if session.view === 'data'}<DataTab />
    {:else}<ReportView preview />{/if}
  </div>
</div>

<style>
  .builder { display: grid; gap: 14px; }
  .head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 10px 16px; }
  .titles { display: grid; gap: 2px; }
  .crumbs { display: flex; gap: 6px; font-size: 12.5px; color: var(--text-muted); }
  .crumbs [aria-current] { color: var(--text); }
  .title-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
  h1 { margin: 0; font-family: var(--font-display); font-weight: 400; font-size: 26px; }
  .legend { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 24px; padding: 10px 14px;
    border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface); font-size: 13px; }
  .legend p { margin: 0; max-width: 70ch; }
  .legend dl { margin: 0; display: flex; flex-wrap: wrap; gap: 6px 16px; }
  .legend dl div { display: flex; align-items: center; gap: 6px; }
  .legend dd { margin: 0; color: var(--text-muted); font-size: 12.5px; }
  .tabs { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px; border-radius: var(--radius-md); background: var(--surface-subtle); justify-self: start; }
  .tabs button { display: grid; justify-items: start; gap: 0; min-height: 44px; padding: 4px 16px; border: 0; border-radius: var(--radius-sm);
    background: transparent; color: var(--text-muted); cursor: pointer; text-align: left; }
  .tabs .t { font-weight: 600; font-size: 13.5px; }
  .tabs .s { font-size: 11.5px; }
  .tabs button:hover { color: var(--text); }
  .tabs button.active { background: var(--surface); color: var(--text); box-shadow: 0 0 0 1px var(--border); }
  @media (max-width: 860px) {
    .tabs { justify-self: stretch; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .head > .btn { width: 100%; justify-content: center; }
  }
</style>
