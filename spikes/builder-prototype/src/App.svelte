<script>
  import Mark from './components/Mark.svelte'
  import QuestionsTab from './components/QuestionsTab.svelte'
  import LayoutTab from './components/LayoutTab.svelte'
  import DataTab from './components/DataTab.svelte'
  import PreviewTab from './components/PreviewTab.svelte'
  import {doc} from './lib/state.svelte.js'

  const TABS = [
    {id: 'questions', label: 'Questions'},
    {id: 'layout', label: 'Layout'},
    {id: 'data', label: 'Data'},
    {id: 'preview', label: 'Preview'},
  ]

  // A bare #token opens a tab, so each view can be linked.
  const fromHash = () => TABS.find((t) => `#${t.id}` === location.hash)?.id
  doc.tab = fromHash() ?? doc.tab

  function select(id) {
    doc.tab = id
    try { history.replaceState(null, '', `#${id}`) } catch { /* not allowed in some frames */ }
  }
  function onkeydown(e) {
    const i = TABS.findIndex((t) => t.id === doc.tab)
    const next = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? TABS.length - 1 : null
    if (next === null) return
    e.preventDefault()
    const tab = TABS[(next + TABS.length) % TABS.length]
    select(tab.id)
    document.getElementById(`tab-${tab.id}`)?.focus()
  }
  function publish() {
    doc.notice = 'This is a prototype: nothing is saved or published. In Skjald, publishing creates version 4 and keeps version 3 for reports already started.'
  }
</script>

<svelte:window onhashchange={() => (doc.tab = fromHash() ?? doc.tab)} />

<div class="shell">
  <header class="top">
    <div class="identity">
      <Mark size={30} />
      <span class="wordmark">Skjald</span>
      <nav class="crumbs" aria-label="Breadcrumb"><span>Templates</span><span aria-hidden="true">›</span><span aria-current="page">Security incident report</span></nav>
      <span class="pill info">Draft of version 4</span>
    </div>
    <div class="tabs" role="tablist" aria-label="Template builder" tabindex="-1" {onkeydown}>
      {#each TABS as t (t.id)}
        <button type="button" role="tab" id="tab-{t.id}" aria-selected={doc.tab === t.id} aria-controls="panel" tabindex={doc.tab === t.id ? 0 : -1}
          class:active={doc.tab === t.id} onclick={() => select(t.id)}>{t.label}</button>
      {/each}
    </div>
    <button type="button" class="btn accent" onclick={publish}>Publish version 4</button>
  </header>

  <p class="notice" role="status" aria-live="polite">
    {#if doc.notice}<span>{doc.notice}</span><button type="button" class="btn quiet" onclick={() => (doc.notice = '')}>Dismiss</button>{/if}
  </p>

  <main>
    <div id="panel" role="tabpanel" aria-labelledby="tab-{doc.tab}">
      {#if doc.tab === 'questions'}<QuestionsTab />
      {:else if doc.tab === 'layout'}<LayoutTab />
      {:else if doc.tab === 'data'}<DataTab />
      {:else}<PreviewTab />{/if}
    </div>
  </main>

  <footer class="foot">Phase 0 prototype of the Skjald template builder. Fictional sample data; nothing leaves this page.</footer>
</div>

<style>
  .shell { max-width: 1520px; margin: 0 auto; display: grid; gap: 12px;
    padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 14px 28px; }
  .top { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 20px;
    padding: 10px 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
  .identity { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; min-width: 0; }
  .wordmark { font-family: var(--font-display); font-size: 22px; line-height: 1; }
  .crumbs { display: flex; gap: 6px; font-size: 13px; color: var(--text-muted); }
  .crumbs [aria-current] { color: var(--text); font-weight: 600; }
  .tabs { display: flex; gap: 2px; padding: 3px; border-radius: var(--radius-md); background: var(--surface-subtle); }
  .tabs button { min-height: 32px; padding: 0 14px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); font-weight: 600; font-size: 13px; cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.active { background: var(--surface); color: var(--text); box-shadow: 0 0 0 1px var(--border); }
  .notice { margin: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; font-size: 13px; }
  .notice span { padding: 8px 12px; border-radius: var(--radius-md); background: var(--info-bg); color: var(--info-text); }
  main { min-width: 0; }
  .foot { font-size: 12px; color: var(--text-muted); text-align: center; }
  @media (max-width: 860px) {
    .tabs { width: 100%; }
    .tabs button { flex: 1; padding: 0 6px; }
    .top > .btn { width: 100%; justify-content: center; }
  }
</style>
